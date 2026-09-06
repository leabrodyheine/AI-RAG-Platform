from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Response
from rag_observability import (
    current_request_id,
    get_tracer,
    observe_retrieval_query,
    record_cache_event,
)

from retrieval_service.cache import RetrievalCache
from retrieval_service.database import DocumentStore
from retrieval_service.dependencies import get_document_store, get_retrieval_cache
from retrieval_service.schemas import SearchRequest, SearchResponse, SearchResult
from retrieval_service.search import search_documents

router = APIRouter(tags=["search"])
_tracer = get_tracer("retrieval.search")

_SERVICE = "retrieval"


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
    request_id = caller_request_id or current_request_id() or str(uuid4())
    response.headers["X-Request-ID"] = request_id

    started = perf_counter()
    with _tracer.start_as_current_span("retrieval.search") as span:
        span.set_attribute("retrieval.top_k", payload.top_k)

        if document_store is None:
            served_by = "memory"
            cache_status = "BYPASS"
            with _tracer.start_as_current_span("retrieval.keyword_search"):
                ranked_documents = search_documents(payload.query, payload.top_k)
        elif retrieval_cache is None:
            served_by = "postgres"
            cache_status = "BYPASS"
            with _tracer.start_as_current_span("retrieval.vector_search"):
                ranked_documents = await document_store.search(payload.query, payload.top_k)
        else:
            corpus_generation = await document_store.corpus_generation()
            with _tracer.start_as_current_span("retrieval.cache_lookup"):
                cached = await retrieval_cache.lookup(
                    payload.query,
                    payload.top_k,
                    document_store.embedding_version,
                    corpus_generation,
                )
            cache_status = cached.status
            if cached.status == "HIT":
                served_by = "cache"
                ranked_documents = cached.results or []
            else:
                served_by = "postgres"
                with _tracer.start_as_current_span("retrieval.vector_search"):
                    ranked_documents = await document_store.search(
                        payload.query, payload.top_k
                    )
                if cached.status == "MISS":
                    with _tracer.start_as_current_span("retrieval.cache_store"):
                        stored = await retrieval_cache.store(
                            payload.query,
                            payload.top_k,
                            document_store.embedding_version,
                            corpus_generation,
                            ranked_documents,
                        )
                    if not stored:
                        cache_status = "BYPASS"

        response.headers["X-Cache"] = cache_status
        span.set_attribute("retrieval.path", served_by)
        span.set_attribute("retrieval.cache_status", cache_status)
        span.set_attribute("retrieval.result_count", len(ranked_documents))

    elapsed = perf_counter() - started
    observe_retrieval_query(_SERVICE, served_by, elapsed)
    record_cache_event(_SERVICE, cache_status.lower())

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
