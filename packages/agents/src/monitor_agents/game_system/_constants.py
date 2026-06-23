"""Constants for game-system action routing (signal regexes)."""

from __future__ import annotations

import re

# Generic action words that map loosely to "physical / non-social" intent
# when skills don't give us better signal.
SOCIAL_SIGNALS = re.compile(
    r"\b(ask|say|talk|tell|speak|persuade|convince|bluff|threaten|charm|"
    r"negotiate|deceive|intimidate|taunt|plead|argue|beg|lie|flatter|court|parley)\b",
    re.IGNORECASE,
)

SHIP_SIGNALS = re.compile(
    r"\b(ship|helm|broadside|boarding|engine|reactor|port|starboard|dock|pilot|reroute)\b",
    re.IGNORECASE,
)

COMBAT_SIGNALS = re.compile(
    r"\b(attack|strike|shoot|stab|slash|fight|charge|block|parry|fire)\b",
    re.IGNORECASE,
)
