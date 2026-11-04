"""Code checks on claims (Q2). They can raise a doubt about a claim, and never approve one.

Code can't establish that a claim is true, but it can show that a number or name isn't in the
source, or that the source limits something the claim states flatly. These only look at wording,
so a flag means "look closer" and not "wrong".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
_NUMBER = re.compile(r"\b(\d+|" + "|".join(_NUMBER_WORDS) + r")\b", re.IGNORECASE)
_OVERSTUFFED_WORDS_ADDED = 25
_COMBINED_WORDS_ADDED = 12
_MIN_STEM = 3
_BOOK_DESCRIPTION = re.compile(
    r"^(?:(?:this|the following|the next|the previous|that)\s+(?:section|chapter|page|sidebar|table)\b"
    r"|(?:see|refer to)\s+(?:page|chapter|the\s+section)\b)"
    r"|\b(?:described|explained|detailed|covered)\s+(?:later|earlier|below|above)\b"
    r"|\b(?:later|earlier)\s+in\s+this\s+(?:chapter|section|book)\b",
    re.IGNORECASE,
)
_CLOSE_MATCH = 0.4
_COMMON_WORDS = frozenset("a an the is are of to in and or for with using use it its this that be can may".split())
_NAME = re.compile(r"(?<=[a-z,] )[A-Z][a-z]{2,}\b")


class Flag(StrEnum):
    NUMBER_NOT_IN_SOURCE = "number_not_in_source"
    NAME_NOT_IN_SOURCE = "name_not_in_source"


@dataclass(frozen=True)
class ClaimFlag:
    flag: Flag
    detail: str


def _numbers(text: str) -> set[int]:
    return {int(found) if found.isdigit() else _NUMBER_WORDS[found.casefold()] for found in _NUMBER.findall(text)}


def check_numbers(statement: str, source: str) -> list[ClaimFlag]:
    """Flag each number in the claim that the source doesn't state, in digits or words."""
    # "One" is usually a determiner ("one possible trait"), so it can't show a wrong number.
    claimed = {n for n in _numbers(statement) if n != 1 or re.search(r"\b1\b", statement)}
    missing = claimed - _numbers(source)
    return [ClaimFlag(Flag.NUMBER_NOT_IN_SOURCE, str(n)) for n in sorted(missing)]


def _word_forms(word: str) -> set[str]:
    """A capitalized verb such as "Keeps" is the same word as "Keep" in the source."""
    lower = word.casefold()
    forms = {lower}
    for ending in ("s", "es", "ed", "ing"):
        stem = lower.removesuffix(ending)
        if stem != lower and len(stem) >= _MIN_STEM:
            forms.add(stem)
    return forms


def check_names(statement: str, source: str, heading: str = "") -> list[ClaimFlag]:
    """Flag a mid-sentence capitalized name that neither the source nor its heading contains."""
    known = f"{source} {heading}".casefold()
    return [
        ClaimFlag(Flag.NAME_NOT_IN_SOURCE, name)
        for name in sorted(set(_NAME.findall(statement)))
        if not any(form in known for form in _word_forms(name))
    ]


def unresolved_flags(statement: str, source: str, section: str) -> list[ClaimFlag]:
    """Find what a final claim asserts beyond its source. Conditions can't be settled here.

    A number must be in the source itself. A name only has to be in the section, because a claim
    resolves "it" or "she" to a name given earlier.
    """
    return [*check_numbers(statement, source), *check_names(statement, section)]


def quote_is_in(quote: str, paragraph: str) -> bool:
    """True when a quote really is in the paragraph, ignoring case and spacing."""
    wanted = " ".join(quote.casefold().split())
    return bool(wanted) and wanted in " ".join(paragraph.casefold().split())


def closely_matches(statement: str, cited_sentences: str) -> bool:
    """True when most of a claim's meaningful words are in the sentences it cites."""
    claimed = _meaningful_words(statement)
    if not claimed:
        return False
    return len(claimed & _meaningful_words(cited_sentences)) / len(claimed) >= _CLOSE_MATCH


def _meaningful_words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.casefold())) - _COMMON_WORDS


def describes_the_book(statement: str) -> bool:
    """True when a claim is about the book's layout, not about the game or the setting."""
    return bool(_BOOK_DESCRIPTION.search(statement.strip()))


def combines_rules(longest_member: str, canonical: str) -> bool:
    """True when a merged statement has grown past what merging one claim's wordings would need."""
    before = len(longest_member.split())
    after = len(canonical.split())
    return after - before >= _COMBINED_WORDS_ADDED and after >= before * 1.5


def is_overstuffed(original: str, corrected: str) -> bool:
    """True when a correction grew so much that it has likely packed in separate rules."""
    before = len(original.split())
    after = len(corrected.split())
    return after - before >= _OVERSTUFFED_WORDS_ADDED and after >= before * 2
