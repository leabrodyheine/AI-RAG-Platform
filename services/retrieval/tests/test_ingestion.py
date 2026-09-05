import pytest
from retrieval_service.ingestion import chunk_document
from retrieval_service.schemas import DocumentInput


def make_document(content: str) -> DocumentInput:
    return DocumentInput(
        id="benchmark-1",
        title="Benchmark",
        source="evaluation/benchmark.json",
        content=content,
    )


def test_short_document_produces_one_stable_chunk() -> None:
    chunks = chunk_document(
        make_document("retrieval latency improved"), chunk_size=5, overlap=0
    )

    assert len(chunks) == 1
    assert chunks[0].id == "benchmark-1:chunk:0"
    assert chunks[0].content == "retrieval latency improved"


def test_long_document_produces_overlapping_chunks() -> None:
    chunks = chunk_document(
        make_document("zero one two three four five six seven"),
        chunk_size=5,
        overlap=2,
    )

    assert [chunk.content for chunk in chunks] == [
        "zero one two three four",
        "three four five six seven",
    ]
    assert [chunk.index for chunk in chunks] == [0, 1]


def test_default_chunking_covers_long_content_without_redundant_chunks() -> None:
    words = [f"word-{index}" for index in range(241)]

    chunks = chunk_document(make_document(" ".join(words)))

    assert len(chunks) == 3
    assert chunks[0].content.split()[-20:] == chunks[1].content.split()[:20]
    assert chunks[1].content.split()[-20:] == chunks[2].content.split()[:20]
    assert chunks[-1].content.split()[-1] == "word-240"


@pytest.mark.parametrize(
    ("chunk_size", "overlap"),
    [(0, 0), (5, -1), (5, 5), (5, 6)],
)
def test_chunking_rejects_invalid_boundaries(chunk_size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_document(make_document("valid content"), chunk_size=chunk_size, overlap=overlap)
