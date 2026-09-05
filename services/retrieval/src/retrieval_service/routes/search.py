from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Header, Response

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
) -> SearchResponse:
    request_id = caller_request_id or str(uuid4())
    response.headers["X-Request-ID"] = request_id

    results = [
        SearchResult(
            id=result.document.id,
            title=result.document.title,
            source=result.document.source,
            excerpt=result.document.content,
            relevance=result.relevance,
        )
        for result in search_documents(payload.query, payload.top_k)
    ]
    return SearchResponse(results=results)
