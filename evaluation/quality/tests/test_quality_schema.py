import json
from pathlib import Path

import pytest

from evaluation.quality.schema import (
    SCHEMA_VERSION,
    DatasetError,
    load_dataset,
    parse_dataset,
)

DATASET_PATH = Path(__file__).resolve().parents[2] / "datasets" / "quality-core-v1.json"


def _valid_payload() -> dict:
    return {
        "schema": SCHEMA_VERSION,
        "version": "unit-v1",
        "embedding_version": "in-memory-keyword-v1",
        "notes": "",
        "cases": [
            {
                "id": "d1",
                "question": "What can you do?",
                "kind": "direct",
                "reference_answer": "It describes itself.",
                "answer_must_include": ["evaluation results"],
            },
            {
                "id": "r1",
                "question": "How much did p95 rise?",
                "kind": "retrieval",
                "reference_answer": "From 112 ms to 391 ms.",
                "expected_evidence": ["retrieval-benchmark-1842"],
                "answer_must_include": ["391 ms"],
            },
            {
                "id": "w1",
                "question": "Why did the cache p95 regress so badly under load?",
                "kind": "rewrite",
                "reference_answer": "Cache misses drove p95 up.",
                "expected_evidence": ["retrieval-benchmark-1842"],
            },
            {
                "id": "i1",
                "question": "What is the capital of France?",
                "kind": "insufficient",
                "reference_answer": "Out of scope.",
                "answer_must_include": ["does not support an answer"],
            },
        ],
    }


def test_committed_dataset_loads_and_covers_every_kind() -> None:
    dataset = load_dataset(DATASET_PATH)

    assert dataset.version == "core-v1"
    assert dataset.embedding_version == "in-memory-keyword-v1"
    assert len(dataset.sha256) == 64
    assert dataset.source_path == DATASET_PATH
    kinds = {case.kind for case in dataset.cases}
    assert kinds == {"direct", "retrieval", "rewrite", "insufficient"}
    assert {c.id for c in dataset.cases if c.id in {"", None}} == set()


def test_committed_dataset_case_ids_are_unique() -> None:
    dataset = load_dataset(DATASET_PATH)
    ids = [case.id for case in dataset.cases]
    assert len(ids) == len(set(ids))


def test_retrieving_cases_name_expected_evidence() -> None:
    dataset = load_dataset(DATASET_PATH)
    for case in dataset.cases:
        if case.kind in {"retrieval", "rewrite"}:
            assert case.expected_evidence, case.id
        else:
            assert case.expected_evidence == (), case.id


def test_parse_dataset_round_trips_a_valid_payload() -> None:
    dataset = parse_dataset(_valid_payload())
    assert [case.id for case in dataset.cases] == ["d1", "r1", "w1", "i1"]
    assert dataset.by_kind("retrieval")[0].answer_must_include == ("391 ms",)


def test_unknown_schema_version_is_rejected() -> None:
    payload = _valid_payload()
    payload["schema"] = "quality-eval-record/v99"
    with pytest.raises(DatasetError, match="unsupported dataset schema"):
        parse_dataset(payload)


def test_duplicate_case_ids_are_rejected() -> None:
    payload = _valid_payload()
    payload["cases"][1]["id"] = "d1"
    with pytest.raises(DatasetError, match="duplicate case id"):
        parse_dataset(payload)


def test_retrieval_case_without_expected_evidence_is_rejected() -> None:
    payload = _valid_payload()
    del payload["cases"][1]["expected_evidence"]
    with pytest.raises(DatasetError, match="must list expected_evidence"):
        parse_dataset(payload)


def test_direct_case_with_expected_evidence_is_rejected() -> None:
    payload = _valid_payload()
    payload["cases"][0]["expected_evidence"] = ["retrieval-benchmark-1842"]
    with pytest.raises(DatasetError, match="must not list expected_evidence"):
        parse_dataset(payload)


def test_unknown_case_field_is_rejected() -> None:
    payload = _valid_payload()
    payload["cases"][0]["expcted_evidence"] = ["typo"]
    with pytest.raises(DatasetError, match="unknown field"):
        parse_dataset(payload)


def test_missing_case_kind_family_is_rejected() -> None:
    payload = _valid_payload()
    payload["cases"] = [case for case in payload["cases"] if case["kind"] != "rewrite"]
    with pytest.raises(DatasetError, match="missing: rewrite"):
        parse_dataset(payload)


def test_blank_question_is_rejected() -> None:
    payload = _valid_payload()
    payload["cases"][0]["question"] = "   "
    with pytest.raises(DatasetError, match="question must be a non-empty string"):
        parse_dataset(payload)


def test_load_dataset_reports_unreadable_file(tmp_path: Path) -> None:
    with pytest.raises(DatasetError, match="cannot read dataset"):
        load_dataset(tmp_path / "missing.json")


def test_load_dataset_reports_invalid_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(DatasetError, match="not valid JSON"):
        load_dataset(bad)


def test_load_dataset_hash_matches_file_bytes() -> None:
    import hashlib

    expected = hashlib.sha256(DATASET_PATH.read_bytes()).hexdigest()
    assert load_dataset(DATASET_PATH).sha256 == expected


def test_committed_dataset_is_pretty_printed_json() -> None:
    # Guards against an accidental one-line commit that would be unreviewable.
    text = DATASET_PATH.read_text(encoding="utf-8")
    assert text.startswith("{\n")
    json.loads(text)
