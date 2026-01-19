"""
Dice rolling utility for MONITOR.

LAYER: 1 (data-layer)
"""

import math
import re
import random
from typing import Dict, Any, List

class DiceResult:
    def __init__(self, total: int, rolls: List[int], expression: str):
        self.total = total
        self.rolls = rolls
        self.expression = expression

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "rolls": self.rolls,
            "expression": self.expression
        }

def roll_dice(expression: str) -> DiceResult:
    """
    Roll dice based on a standard expression (e.g., '1d20', '2d6+5').
    Currently supports simple 'NdS' format.
    """
    # Simple regex for NdS
    match = re.search(r'(\d+)d(\d+)', expression)
    if not match:
        # Try finding just a number (static bonus?) or handle error
        # For now, simplistic implementation
        return DiceResult(0, [], expression)
    
    amount = int(match.group(1))
    sides = int(match.group(2))
    
    rolls = [random.randint(1, sides) for _ in range(amount)]
    total = sum(rolls)
    
    # Check for modifier (+X or -X)
    # This is a very basic parser, can be expanded
    if '+' in expression:
        try:
            mod = int(expression.split('+')[1])
            total += mod
        except (ValueError, IndexError):
            pass
    
    return DiceResult(total, rolls, expression)

def calculate_modifier(value: int, formula: str) -> int:
    """
    Calculate a modifier based on a value and a formula string.
    Supported placeholders: VALUE
    Example: "(VALUE - 10) // 2"

    Note: Uses eval() with restricted environment for formula evaluation.
    Formulas are expected to come from trusted admin-defined game systems.
    """
    # Safety: Only allow basic math operations
    safe_env = {
        "VALUE": value,
        "__builtins__": None,
        "__name__": None,
        "__file__": None,
        "__loader__": None,
    }

    try:
        # Evaluate the formula (expected from trusted game system JSON)
        result = eval(formula, {"__builtins__": {}}, safe_env)
        # Use floor to correctly handle negative modifiers (e.g., -0.5 → -1, not 0)
        return math.floor(result) if isinstance(result, float) else int(result)
    except (ValueError, TypeError, SyntaxError, NameError) as e:
        # Log the error in production, return safe default
        return 0
