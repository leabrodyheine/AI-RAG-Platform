import pytest
from pydantic import ValidationError
from retrieval_service.schemas import DocumentInput, IngestDocumentsRequest


def document_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "benchmark-1",
        "title": "Benchmark result",
        "source": "evaluation/result.json",
        "content": "Retrieval p95 was 120 ms.",
        "tags": ["retrieval", "latency"],
    }
    payload.update(overrides)
    return payload


def test_ingestion_models_strip_text_and_preserve_tags() -> None:
    request = IngestDocumentsRequest.model_validate(
        {"documents": [document_payload(title="  Benchmark result  ")]}
    )

    assert request.documents[0].title == "Benchmark result"
    assert request.documents[0].tags == ("retrieval", "latency")


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": ""},
        {"title": " "},
        {"source": "x" * 501},
        {"content": "x" * 20_001},
        {"tags": ["duplicate", "duplicate"]},
        {"tags": ["x" * 65]},
        {"unexpected": True},
    ],
)
def test_ingestion_rejects_invalid_documents(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        DocumentInput.model_validate(document_payload(**overrides))


def test_ingestion_rejects_an_empty_batch() -> None:
    with pytest.raises(ValidationError):
        IngestDocumentsRequest(documents=[])


def test_ingestion_rejects_duplicate_document_ids() -> None:
    document = DocumentInput.model_validate(document_payload())

    with pytest.raises(ValidationError):
        IngestDocumentsRequest(documents=[document, document])
