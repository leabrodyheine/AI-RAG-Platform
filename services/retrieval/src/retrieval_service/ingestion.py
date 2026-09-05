"""Stable document chunking for vector indexing."""

from dataclasses import dataclass

from retrieval_service.corpus import EvaluationDocument
from retrieval_service.schemas import DocumentInput

CHUNK_SIZE_WORDS = 120
CHUNK_OVERLAP_WORDS = 20


@dataclass(frozen=True)
class DocumentChunk:
    document_id: str
    index: int
    content: str

    @property
    def id(self) -> str:
        return f"{self.document_id}:chunk:{self.index}"


def chunk_document(
    document: DocumentInput | EvaluationDocument,
    *,
    chunk_size: int = CHUNK_SIZE_WORDS,
    overlap: int = CHUNK_OVERLAP_WORDS,
) -> tuple[DocumentChunk, ...]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be greater than zero")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")

    words = document.content.split()
    step = chunk_size - overlap
    chunks: list[DocumentChunk] = []
    for index, start in enumerate(range(0, len(words), step)):
        chunks.append(
            DocumentChunk(
                document_id=document.id,
                index=index,
                content=" ".join(words[start : start + chunk_size]),
            )
        )
        if start + chunk_size >= len(words):
            break
    return tuple(chunks)
