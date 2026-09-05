from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Response

from retrieval_service.cache import RetrievalCache
from retrieval_service.database import DocumentStore
from retrieval_service.dependencies import get_document_store, get_retrieval_cache
from retrieval_service.schemas import SearchRequest, SearchResponse, SearchResult
from retrieval_service.search import search_documents

router = APIRouter(tags=["search"])


@router.post(
    "/search",
    operation_id="searchEvidence",
    summary="Search evaluation evidence",
    response_model=SearchResponse,
)
async def search(
    payload: SearchRequest,
    response: Response,
    caller_request_id: Annotated[
        str | None,
        Header(alias="X-Request-ID", min_length=1, max_length=128),
    ] = None,
    document_store: Annotated[DocumentStore | None, Depends(get_document_store)] = None,
    retrieval_cache: Annotated[RetrievalCache | None, Depends(get_retrieval_cache)] = None,
) -> SearchResponse:
    request_id = caller_request_id or str(uuid4())
    response.headers["X-Request-ID"] = request_id

    if document_store is None:
        response.headers["X-Cache"] = "BYPASS"
        ranked_documents = search_documents(payload.query, payload.top_k)
    elif retrieval_cache is None:
        response.headers["X-Cache"] = "BYPASS"
        ranked_documents = await document_store.search(payload.query, payload.top_k)
    else:
        corpus_generation = await document_store.corpus_generation()
        cached = await retrieval_cache.lookup(
            payload.query,
            payload.top_k,
            document_store.embedding_version,
            corpus_generation,
        )
        response.headers["X-Cache"] = cached.status
        if cached.status == "HIT":
            ranked_documents = cached.results or []
        else:
            ranked_documents = await document_store.search(payload.query, payload.top_k)
            if cached.status == "MISS":
                stored = await retrieval_cache.store(
                    payload.query,
                    payload.top_k,
                    document_store.embedding_version,
                    corpus_generation,
                    ranked_documents,
                )
                if not stored:
                    response.headers["X-Cache"] = "BYPASS"
    results = [
        SearchResult(
            id=result.document.id,
            title=result.document.title,
            source=result.document.source,
            excerpt=result.document.content,
            relevance=result.relevance,
        )
        for result in ranked_documents
    ]
    return SearchResponse(results=results)
