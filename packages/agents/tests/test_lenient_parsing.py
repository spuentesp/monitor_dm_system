"""Lenient parsing: unknown enum → other, JSON string → object, batch not lost (I-2, I-3).

The two exact live failures from 2026-11-10: ExtractedEntityArchetype.group_type
came back as "corp", and a list[ExtractedAxiom] came back as JSON strings. Both
each cost a whole extraction batch.
"""

from __future__ import annotations

import pytest
import structlog
from dspy.utils.exceptions import AdapterParseError
from monitor_agents.lenient_parsing import (
    Repair,
    lenient_validate,
    recover_parse_failure,
)
from monitor_data.schemas.book_graph import ExtractedAtom
from monitor_data.schemas.entity_subtypes import GroupType
from monitor_data.schemas.knowledge_packs import ExtractedAxiom, ExtractedEntityArchetype
from pydantic import ValidationError

# The exact payload the model produced for one live failure.
GROUP_TYPE_CORP = {
    "name": "MegaCorp",
    "entity_type": "organization",
    "sub_type": "corp",
    "group_type": "corp",
}

# The exact payload shape for the other live failure: items as JSON strings.
AXIOMS_AS_JSON_STRINGS = [
    '{"statement": "Magic exists", "domain": "magic"}',
    '{"statement": "The gods are real", "domain": "religion"}',
]


@pytest.mark.unit
def test_group_type_corp_maps_to_other_and_keeps_the_item() -> None:
    payload = dict(GROUP_TYPE_CORP)

    item, repairs = lenient_validate(ExtractedEntityArchetype, payload)

    assert isinstance(item, ExtractedEntityArchetype)
    assert item.group_type == GroupType.OTHER
    assert repairs == [Repair(path="group_type", kind="unknown_enum", original="corp", repaired="other")]
    # The caller's payload is left untouched.
    assert payload["group_type"] == "corp"


@pytest.mark.unit
def test_axioms_received_as_json_strings_are_parsed_and_recorded() -> None:
    items, repairs = lenient_validate(list[ExtractedAxiom], AXIOMS_AS_JSON_STRINGS)

    assert [axiom.statement for axiom in items] == ["Magic exists", "The gods are real"]
    assert repairs == [
        Repair(path="[0]", kind="json_string", original=AXIOMS_AS_JSON_STRINGS[0], repaired=repairs[0].repaired),
        Repair(path="[1]", kind="json_string", original=AXIOMS_AS_JSON_STRINGS[1], repaired=repairs[1].repaired),
    ]
    assert all(repair.kind == "json_string" for repair in repairs)


@pytest.mark.unit
def test_valid_payload_is_untouched_and_repairs_empty() -> None:
    payload = {"name": "Wizard", "entity_type": "character"}

    item, repairs = lenient_validate(ExtractedEntityArchetype, payload)

    assert item.name == "Wizard"
    assert item.group_type is None
    assert repairs == []


@pytest.mark.unit
def test_unknown_enum_without_other_member_still_rejects() -> None:
    """AtomKind has no OTHER member: the schema must still say no."""
    payload = {"kind": "bogus", "statement": "s", "cites": ["S1"]}

    with pytest.raises(ValidationError):
        lenient_validate(ExtractedAtom, payload)


@pytest.mark.unit
def test_unparsable_json_string_is_left_for_the_schema_to_reject() -> None:
    with pytest.raises(ValidationError):
        lenient_validate(list[ExtractedAxiom], ["not json at all"])


# ---------------------------------------------------------------------------
# Application: recover_parse_failure, used by analyzer._call_module
# ---------------------------------------------------------------------------

_BATCHED_COMPLETION = """\
[[ ## extraction_reasoning ## ]]
The sections state world rules and organizations.

[[ ## axioms ## ]]
["{\\"statement\\": \\"Magic exists\\", \\"domain\\": \\"magic\\"}"]

[[ ## entities ## ]]
[{"name": "MegaCorp", "entity_type": "organization", "sub_type": "corp", "group_type": "corp"}]

[[ ## lore_facts ## ]]
[]

[[ ## sections_covered ## ]]
["Rules > Magic"]

[[ ## completed ## ]]
"""


def _parse_error(completion: str) -> AdapterParseError:
    from monitor_agents.analyzer.analyzer import BatchedExtractionSignature

    return AdapterParseError("ChatAdapter", BatchedExtractionSignature, completion)


@pytest.mark.unit
def test_recovery_repairs_both_live_failures_in_one_completion() -> None:
    prediction = recover_parse_failure(_parse_error(_BATCHED_COMPLETION))

    assert prediction is not None
    assert [axiom.statement for axiom in prediction.axioms] == ["Magic exists"]
    assert prediction.entities[0].group_type == GroupType.OTHER
    assert prediction.lore_facts == []
    assert "world rules" in prediction.extraction_reasoning


@pytest.mark.unit
def test_recovery_logs_one_record_per_repair() -> None:
    with structlog.testing.capture_logs() as logs:
        recover_parse_failure(_parse_error(_BATCHED_COMPLETION))

    repairs = [entry for entry in logs if entry["event"] == "lenient_parse_repair"]
    kinds = {entry["kind"] for entry in repairs}
    assert "unknown_enum" in kinds
    assert "json_string" in kinds
    assert any(entry["path"].startswith("entities") and entry["original"] == "corp" for entry in repairs)
    assert any(entry["path"].startswith("axioms") for entry in repairs)


@pytest.mark.unit
@pytest.mark.parametrize(
    "completion",
    ["", "   ", "Sorry, I cannot help with that request."],
)
def test_recovery_refuses_to_invent_fields(completion: str) -> None:
    assert recover_parse_failure(_parse_error(completion)) is None


@pytest.mark.unit
def test_recovery_returns_none_when_an_output_field_is_missing() -> None:
    completion = """\
[[ ## extraction_reasoning ## ]]
Because.

[[ ## axioms ## ]]
[]

[[ ## entities ## ]]
[]

[[ ## completed ## ]]
"""
    # lore_facts section is missing entirely.
    assert recover_parse_failure(_parse_error(completion)) is None


@pytest.mark.unit
def test_recovery_returns_none_for_an_exception_without_a_completion() -> None:
    assert recover_parse_failure(RuntimeError("boom")) is None


@pytest.mark.unit
async def test_call_module_returns_the_recovered_prediction_without_retrying(monkeypatch) -> None:
    """Cross-component: _call_module must consult recover_parse_failure before retrying."""
    from monitor_agents.analyzer import Analyzer

    analyzer = Analyzer()

    class _Runner:
        def __init__(self) -> None:
            self.calls = 0

        async def run_blocking(self, operation, *, kwargs, context, timeout=None, on_attempt=None):
            self.calls += 1
            raise _parse_error(_BATCHED_COMPLETION)

    runner = _Runner()
    monkeypatch.setattr(analyzer, "_llm_runner", runner)

    prediction = await analyzer._call_module(object(), sections_context="x")

    assert runner.calls == 1  # recovered on the first failure: no unchanged retry
    assert [axiom.statement for axiom in prediction.axioms] == ["Magic exists"]
    assert prediction.entities[0].group_type == GroupType.OTHER


@pytest.mark.unit
def test_a_reply_missing_sections_covered_is_not_recovered() -> None:
    """BatchedExtractionSignature asks for sections_covered so a cut-off reply is
    detected. A completion without it is never accepted as complete: recovery
    returns None and the caller retries or splits the batch."""
    truncated = _BATCHED_COMPLETION.replace('[[ ## sections_covered ## ]]\n["Rules > Magic"]\n\n', "")
    assert "sections_covered" not in truncated

    assert recover_parse_failure(_parse_error(truncated)) is None


# ---------------------------------------------------------------------------
# Recovery from an instructor failure (the G11 pre-flight finding, 2026-11-11)
# ---------------------------------------------------------------------------
#
# The at-the-table Complication lookup (S5) returned 500 because the LIGHT
# tier's 1B model wrote `{"complications": "[\"a\", \"b\"]"}` — a JSON string
# where an array belongs. Instructor retried, the retry returned prose, and
# the whole lookup failed. The answer in generation 1 was one repair away.


class _Fn:
    def __init__(self, arguments: str) -> None:
        self.arguments = arguments


class _ToolCall:
    def __init__(self, arguments: str) -> None:
        self.function = _Fn(arguments)


class _Message:
    def __init__(self, content: str | None = None, tool_calls: list | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls


class _Choice:
    def __init__(self, message: _Message) -> None:
        self.message = message


class _Completion:
    def __init__(self, message: _Message) -> None:
        self.choices = [_Choice(message)]


class _Attempt:
    def __init__(self, completion: _Completion | None) -> None:
        self.attempt_number = 1
        self.exception = ValueError("validation error")
        self.completion = completion


class _InstructorFailure(Exception):
    def __init__(self, attempts: list[_Attempt]) -> None:
        super().__init__("failed_attempts")
        self.failed_attempts = attempts


class _Suggestions:
    """The shape the lookup asks for: a list of strings plus a rationale."""

    def __init__(self, complications: list[str], rationale: str = "") -> None:
        self.complications = complications
        self.rationale = rationale

    @classmethod
    def model_validate(cls, payload: dict) -> "_Suggestions":
        from pydantic import BaseModel, Field

        class _M(BaseModel):
            complications: list[str] = Field(default_factory=list)
            rationale: str = ""

        parsed = _M.model_validate(payload)
        return cls(complications=parsed.complications, rationale=parsed.rationale)


from pydantic import BaseModel, Field  # noqa: E402


class _SuggestionsModel(BaseModel):
    complications: list[str] = Field(default_factory=list)
    rationale: str = ""


@pytest.mark.unit
def test_a_json_string_where_a_list_belongs_is_recovered() -> None:
    """The exact failure the pre-flight found: `[...]` as a string."""
    completion = _Completion(
        _Message(
            tool_calls=[
                _ToolCall('{"complications": "[\\"The players are held hostage\\", \\"The notes are burnt\\"]", "rationale": "raise the stakes"}')
            ]
        )
    )
    exc = _InstructorFailure([_Attempt(completion)])

    from monitor_agents.lenient_parsing import recover_instructor_failure

    recovered = recover_instructor_failure(exc, _SuggestionsModel)

    assert recovered is not None
    assert recovered.complications == ["The players are held hostage", "The notes are burnt"]


@pytest.mark.unit
def test_an_answer_stored_as_message_body_is_recovered() -> None:
    """A text provider puts the JSON in the message body, not a tool call."""
    completion = _Completion(
        _Message(content='{"complications": ["a", "b"], "rationale": "why"}')
    )
    exc = _InstructorFailure([_Attempt(completion)])

    from monitor_agents.lenient_parsing import recover_instructor_failure

    recovered = recover_instructor_failure(exc, _SuggestionsModel)

    assert recovered is not None
    assert recovered.complications == ["a", "b"]


@pytest.mark.unit
def test_an_unrecoverable_attempt_returns_none() -> None:
    """A prose answer has nothing to validate — the caller keeps its own error."""
    completion = _Completion(_Message(content="Here are three complications..."))
    exc = _InstructorFailure([_Attempt(completion)])

    from monitor_agents.lenient_parsing import recover_instructor_failure

    assert recover_instructor_failure(exc, _SuggestionsModel) is None


@pytest.mark.unit
def test_an_exception_without_attempts_is_not_recoverable() -> None:
    from monitor_agents.lenient_parsing import recover_instructor_failure

    assert recover_instructor_failure(ValueError("boom"), _SuggestionsModel) is None


@pytest.mark.unit
def test_a_value_wrapped_in_its_own_schema_is_unwrapped() -> None:
    """The second malformation the pre-flight found: {"type": "string", ...}."""
    payload = {
        "complications": [
            {"type": "string", "value": "The players are held hostage"},
            {"type": "string", "value": "The notes are burnt"},
        ]
    }

    item, repairs = lenient_validate(_SuggestionsModel, payload)

    assert item.complications == ["The players are held hostage", "The notes are burnt"]
    assert {repair.kind for repair in repairs} == {"wrapped_scalar"}


@pytest.mark.unit
def test_a_one_item_list_where_a_string_belongs_is_unwrapped() -> None:
    payload = {"complications": [["The players are held hostage"]], "rationale": "raise the stakes"}

    item, repairs = lenient_validate(_SuggestionsModel, payload)

    assert item.complications == ["The players are held hostage"]
    assert any(repair.kind == "single_item_list" for repair in repairs)


@pytest.mark.unit
def test_an_unknown_dict_still_fails_validation() -> None:
    """The repair is a known rule, not "accept anything"."""
    with pytest.raises(ValidationError):
        lenient_validate(_SuggestionsModel, {"complications": [{"nonsense": 1}]})
