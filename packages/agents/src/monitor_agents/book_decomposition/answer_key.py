"""The answer key: hand-checked claims that review changes are scored against (Q1, I-17).

A person's labels are the only authority here. A model pre-fills them to save time, and it must
be a different model from any reviewer being scored, or the key would flatter that reviewer.
Labels live in an append-only file, so the last answer for a claim wins and a crash loses at most
one click.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
from collections import defaultdict
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any

import dspy
import structlog
from monitor_data.schemas.book_graph import BookNode, BookNodeKind, BookTree
from pydantic import BaseModel, Field, ValidationError

from monitor_agents.book_decomposition.extractor import run_metered
from monitor_agents.book_decomposition.pacing import RunGuard, RunStopped
from monitor_agents.book_decomposition.review import Claim

log = structlog.get_logger()

_CONDITION_WORD = re.compile(r"\b(but|unless|except|only|however)\b", re.IGNORECASE)
_PREFILL_BATCH = 10


class Support(StrEnum):
    QUOTED = "quoted"
    ENTAILED = "entailed"
    INFERRED = "inferred"
    UNSUPPORTED = "unsupported"


class Scope(StrEnum):
    GENERAL_RULE = "general_rule"
    SETTING_CANON = "setting_canon"
    SINGLE_EXAMPLE = "single_example"


class Force(StrEnum):
    MUST = "must"
    MAY = "may"
    USUALLY = "usually"
    CANNOT = "cannot"
    NONE = "none"  # States something without any obligation or permission.


class Authority(StrEnum):
    CORE_RULE = "core_rule"
    OPTIONAL_RULE = "optional_rule"
    GM_ADVICE = "gm_advice"
    IN_WORLD_FICTION = "in_world_fiction"


class Labels(BaseModel):
    """The values a person assigns to one claim."""

    support: Support
    scope: Scope
    force: Force
    authority: Authority
    dropped_condition: bool = Field(description="The source limits this, and the claim doesn't say so")
    canon: bool = Field(description="This belongs in canon as written")


class KeyRow(BaseModel):
    """One claim to label, with the text a person needs in order to judge it."""

    id: str
    split: str = Field(description="tuning, or test: never used while changing prompts")
    page: int
    kind: str
    statement: str
    heading: str
    source: str
    before: str = ""
    after: str = ""
    prefill: Labels | None = None


class Answer(BaseModel):
    """A person's decision about one claim."""

    id: str
    labels: Labels
    note: str = ""
    canon_if_corrected: bool | None = Field(
        None, description="For a dropped condition: does the fact belong in canon once restored?"
    )


def select_sample(
    claims: Sequence[Claim], tuning_pages: set[int], *, tuning: int, test: int, seed: int
) -> list[tuple[str, Claim]]:
    """Pick claims for each split, covering every page and kind.

    Claims whose source has a limiting word get up to a third of each split, because dropped
    conditions are rare and are what the key most needs to measure.
    """
    rng = random.Random(seed)  # noqa: S311  # reason: repeatable sampling, not security

    def pick(pool: list[Claim], count: int) -> list[Claim]:
        rng.shuffle(pool)
        conditional = [c for c in pool if _CONDITION_WORD.search(c.source_text)]
        chosen = {c.id: c for c in conditional[: count // 3]}
        groups: dict[tuple[int, str], list[Claim]] = defaultdict(list)
        for claim in pool:
            groups[(claim.page, claim.atom.kind.value)].append(claim)
        while len(chosen) < count and any(groups.values()):
            for group in groups.values():
                if group and len(chosen) < count:
                    claim = group.pop()
                    chosen[claim.id] = claim
        return list(chosen.values())

    tuning_pool = [c for c in claims if c.page + 1 in tuning_pages]
    test_pool = [c for c in claims if c.page + 1 not in tuning_pages]
    sample = [("tuning", c) for c in pick(tuning_pool, tuning)]
    sample += [("test", c) for c in pick(test_pool, test)]
    rng.shuffle(sample)
    return sample


def build_rows(tree: BookTree, sample: Sequence[tuple[str, Claim]]) -> list[KeyRow]:
    """Add each claim's heading and neighboring paragraphs. A running example needs them."""
    by_id = {node.id: node for node in tree.nodes}
    paragraphs = sorted((n for n in tree.nodes if n.kind == BookNodeKind.PARAGRAPH), key=lambda n: n.seq)
    position = {node.id: i for i, node in enumerate(paragraphs)}

    def heading(node: BookNode) -> str:
        parts: list[str] = []
        parent = by_id.get(node.parent_id or "")
        while parent is not None:
            if parent.kind == BookNodeKind.DIVISION:
                parts.append(parent.text)
            parent = by_id.get(parent.parent_id or "")
        return " > ".join(reversed(parts))

    rows = []
    for split, claim in sample:
        node = by_id[claim.source_node_ids[0]]
        paragraph = by_id.get(node.parent_id or "") if node.kind == BookNodeKind.SENTENCE else node
        index = position.get(paragraph.id) if paragraph else None
        before = paragraphs[index - 1].text if index else ""
        after = paragraphs[index + 1].text if index is not None and index + 1 < len(paragraphs) else ""
        rows.append(
            KeyRow(
                id=claim.id,
                split=split,
                page=claim.page + 1,
                kind=claim.atom.kind.value,
                statement=claim.atom.statement,
                heading=heading(node),
                source=claim.source_text,
                before=before,
                after=after,
            )
        )
    return rows


class _PrefillItem(BaseModel):
    label: str
    labels: Labels


class _PrefillBatch(BaseModel):
    items: list[_PrefillItem] = Field(default_factory=list)


class _PrefillSignature(dspy.Signature):  # type: ignore[misc]
    """Label claims extracted from a tabletop RPG book. A person will check your labels.

    support: quoted (nearly the source's own words), entailed (necessarily follows), inferred (a
    reasonable reading it doesn't state), unsupported (the source doesn't say this).
    scope: general_rule (applies in any game), setting_canon (true of the setting), single_example
    (what one illustrative character or scene does; check the surrounding text, because a running
    example may have no "Example:" label).
    force: must, may, usually, cannot, or none when it only states something.
    authority: core_rule, optional_rule, gm_advice, or in_world_fiction.
    dropped_condition: true if the source limits this claim and the claim doesn't say so.
    canon: true if this belongs in canon exactly as written.

    Return one item per claim label.
    """

    claims: str = dspy.InputField(desc="Each claim with its label, heading and surrounding text")
    result: _PrefillBatch = dspy.OutputField()


def format_for_prefill(rows: Sequence[KeyRow]) -> str:
    return "\n\n".join(
        f"[C{i}] kind={row.kind} heading={row.heading}\nBEFORE: {row.before}\n"
        f"SOURCE: {row.source}\nAFTER: {row.after}\nCLAIM: {row.statement}"
        for i, row in enumerate(rows, 1)
    )


async def prefill_rows(rows: list[KeyRow], lm: Any, guard: RunGuard) -> int:
    """Fill in suggested labels. A claim that fails stays blank for a person. Returns the count."""
    predict = dspy.Predict(_PrefillSignature)
    filled = 0
    for start in range(0, len(rows), _PREFILL_BATCH):
        batch = rows[start : start + _PREFILL_BATCH]
        usage = [0, 0]

        async def make_call(current: list[KeyRow] = batch, used: list[int] = usage) -> Any:
            def call() -> Any:
                prediction, used[0], used[1] = run_metered(lm, lambda: predict(claims=format_for_prefill(current)))
                return prediction.result

            return await asyncio.to_thread(call)

        try:
            result = await guard.call(make_call)
        except RunStopped:
            raise
        except Exception as exc:  # noqa: BLE001  # reason: these claims stay blank for a person
            log.warning("answer_key_prefill_failed", error=str(exc)[:200])
            continue
        guard.record(usage[0], usage[1])
        labels = {f"C{i}": row for i, row in enumerate(batch, 1)}
        for item in _PrefillBatch.model_validate(result).items:
            row = labels.get(item.label)
            if row is not None:
                row.prefill = item.labels
                filled += 1
    return filled


def write_rows(path: Path, rows: Sequence[KeyRow]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps([row.model_dump(mode="json") for row in rows], ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def read_rows(path: Path) -> list[KeyRow]:
    return [KeyRow.model_validate(row) for row in json.loads(path.read_text(encoding="utf-8"))]


def append_answer(path: Path, answer: Answer) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(answer.model_dump_json() + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_answers(path: Path) -> dict[str, Answer]:
    """Load the answers, with the last one per claim winning. A torn line is ignored."""
    answers: dict[str, Answer] = {}
    if not path.exists():
        return answers
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            answer = Answer.model_validate_json(line)
        except ValidationError:
            log.warning("answer_key_torn_line", path=str(path))
            continue
        answers[answer.id] = answer
    return answers
