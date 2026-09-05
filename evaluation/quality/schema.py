"""Versioned evaluation-record schema and dataset loader.

A dataset file is JSON:

    {
      "schema": "quality-eval-record/v1",
      "version": "core-v1",
      "embedding_version": "feature-hash-v1",
      "notes": "...",
      "cases": [ { ... EvaluationCase ... }, ... ]
    }

``schema`` is the record-format version and is checked on load; ``version`` is
the dataset's own content version and is recorded in every run so a report can
be tied back to the exact questions that produced it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA_VERSION = "quality-eval-record/v1"

# What the plan calls the four case families:
#   direct        - answered without retrieval (greetings, "what can you do")
#   retrieval     - answerable from a single retrieval pass
#   rewrite       - first retrieval is weak; the one bounded rewrite recovers it
#   insufficient  - no evidence exists; the answer must say so and cite nothing
CASE_KINDS = ("direct", "retrieval", "rewrite", "insufficient")
_RETRIEVING_KINDS = ("retrieval", "rewrite")

_MAX_QUESTION_LENGTH = 4000  # matches the agent's ChatRequest bound


class DatasetError(ValueError):
    """A dataset file is missing, malformed, or fails a schema rule."""


@dataclass(frozen=True)
class EvaluationCase:
    """One scored question.

    ``expected_evidence`` holds retrieval-corpus document ids that a correct
    answer should rest on. ``answer_must_include`` / ``answer_must_not_include``
    are case-insensitive substrings the deterministic judge checks; keep them
    to load-bearing facts (a number, a name) so they survive answer rewording.
    """

    id: str
    question: str
    kind: str
    reference_answer: str
    expected_evidence: tuple[str, ...] = ()
    answer_must_include: tuple[str, ...] = ()
    answer_must_not_include: tuple[str, ...] = ()
    notes: str = ""

    @property
    def needs_retrieval(self) -> bool:
        return self.kind in _RETRIEVING_KINDS


@dataclass(frozen=True)
class EvaluationDataset:
    version: str
    embedding_version: str
    cases: tuple[EvaluationCase, ...]
    notes: str = ""
    source_path: Path | None = field(default=None, compare=False)
    sha256: str = ""

    def by_kind(self, kind: str) -> tuple[EvaluationCase, ...]:
        return tuple(case for case in self.cases if case.kind == kind)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DatasetError(message)


def _string_tuple(value: object, *, field_name: str, case_id: str) -> tuple[str, ...]:
    _require(
        isinstance(value, list) and all(isinstance(item, str) and item for item in value),
        f"case {case_id!r}: {field_name} must be a list of non-empty strings",
    )
    assert isinstance(value, list)  # narrowed by _require above
    return tuple(value)


def _parse_case(raw: object, *, seen_ids: set[str]) -> EvaluationCase:
    _require(isinstance(raw, dict), "each case must be a JSON object")
    assert isinstance(raw, dict)

    case_id = raw.get("id")
    _require(isinstance(case_id, str) and case_id != "", "every case needs a non-empty string id")
    assert isinstance(case_id, str)
    _require(case_id not in seen_ids, f"duplicate case id: {case_id!r}")
    seen_ids.add(case_id)

    allowed = {
        "id",
        "question",
        "kind",
        "reference_answer",
        "expected_evidence",
        "answer_must_include",
        "answer_must_not_include",
        "notes",
    }
    unknown = set(raw) - allowed
    _require(not unknown, f"case {case_id!r}: unknown field(s): {', '.join(sorted(unknown))}")

    question = raw.get("question")
    _require(
        isinstance(question, str) and question.strip() != "",
        f"case {case_id!r}: question must be a non-empty string",
    )
    assert isinstance(question, str)
    _require(
        len(question) <= _MAX_QUESTION_LENGTH,
        f"case {case_id!r}: question exceeds {_MAX_QUESTION_LENGTH} characters",
    )

    kind = raw.get("kind")
    _require(
        kind in CASE_KINDS,
        f"case {case_id!r}: kind must be one of {', '.join(CASE_KINDS)}",
    )
    assert isinstance(kind, str)

    reference_answer = raw.get("reference_answer")
    _require(
        isinstance(reference_answer, str) and reference_answer.strip() != "",
        f"case {case_id!r}: reference_answer must be a non-empty string",
    )
    assert isinstance(reference_answer, str)

    expected_evidence = _string_tuple(
        raw.get("expected_evidence", []), field_name="expected_evidence", case_id=case_id
    )
    must_include = _string_tuple(
        raw.get("answer_must_include", []), field_name="answer_must_include", case_id=case_id
    )
    must_not_include = _string_tuple(
        raw.get("answer_must_not_include", []),
        field_name="answer_must_not_include",
        case_id=case_id,
    )
    notes = raw.get("notes", "")
    _require(isinstance(notes, str), f"case {case_id!r}: notes must be a string")
    assert isinstance(notes, str)

    if kind in _RETRIEVING_KINDS:
        _require(
            bool(expected_evidence),
            f"case {case_id!r}: {kind} cases must list expected_evidence",
        )
    else:
        _require(
            not expected_evidence,
            f"case {case_id!r}: {kind} cases must not list expected_evidence",
        )

    return EvaluationCase(
        id=case_id,
        question=question,
        kind=kind,
        reference_answer=reference_answer,
        expected_evidence=expected_evidence,
        answer_must_include=must_include,
        answer_must_not_include=must_not_include,
        notes=notes,
    )


def parse_dataset(
    payload: object,
    *,
    source_path: Path | None = None,
    sha256: str = "",
) -> EvaluationDataset:
    """Validate an already-decoded dataset object and return it typed."""
    _require(isinstance(payload, dict), "dataset root must be a JSON object")
    assert isinstance(payload, dict)

    schema = payload.get("schema")
    _require(
        schema == SCHEMA_VERSION,
        f"unsupported dataset schema {schema!r}; this build expects {SCHEMA_VERSION!r}",
    )

    version = payload.get("version")
    _require(
        isinstance(version, str) and version.strip() != "",
        "dataset needs a non-empty string 'version'",
    )
    assert isinstance(version, str)

    embedding_version = payload.get("embedding_version")
    _require(
        isinstance(embedding_version, str) and embedding_version.strip() != "",
        "dataset needs a non-empty string 'embedding_version'",
    )
    assert isinstance(embedding_version, str)

    notes = payload.get("notes", "")
    _require(isinstance(notes, str), "dataset 'notes' must be a string")
    assert isinstance(notes, str)

    raw_cases = payload.get("cases")
    _require(
        isinstance(raw_cases, list) and len(raw_cases) > 0,
        "dataset 'cases' must be a non-empty list",
    )
    assert isinstance(raw_cases, list)

    seen_ids: set[str] = set()
    cases = tuple(_parse_case(raw, seen_ids=seen_ids) for raw in raw_cases)

    present_kinds = {case.kind for case in cases}
    missing = [kind for kind in CASE_KINDS if kind not in present_kinds]
    _require(
        not missing,
        f"dataset must cover every case kind; missing: {', '.join(missing)}",
    )

    return EvaluationDataset(
        version=version,
        embedding_version=embedding_version,
        cases=cases,
        notes=notes,
        source_path=source_path,
        sha256=sha256,
    )


def load_dataset(path: str | Path) -> EvaluationDataset:
    """Read, hash, and validate a dataset file."""
    dataset_path = Path(path)
    try:
        raw_bytes = dataset_path.read_bytes()
    except OSError as error:
        raise DatasetError(f"cannot read dataset {dataset_path}: {error}") from error
    try:
        payload = json.loads(raw_bytes)
    except json.JSONDecodeError as error:
        raise DatasetError(f"dataset {dataset_path} is not valid JSON: {error}") from error
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    return parse_dataset(payload, source_path=dataset_path, sha256=sha256)
