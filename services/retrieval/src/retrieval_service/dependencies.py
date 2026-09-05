from typing import cast

from fastapi import Request

from retrieval_service.cache import RetrievalCache
from retrieval_service.database import DocumentStore


def get_document_store(request: Request) -> DocumentStore | None:
    return cast(DocumentStore | None, getattr(request.app.state, "document_store", None))


def get_retrieval_cache(request: Request) -> RetrievalCache | None:
    return cast(RetrievalCache | None, getattr(request.app.state, "retrieval_cache", None))
