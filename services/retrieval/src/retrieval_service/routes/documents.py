from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from retrieval_service.database import DocumentStore
from retrieval_service.dependencies import get_document_store
from retrieval_service.schemas import IngestDocumentsRequest, IngestDocumentsResponse

router = APIRouter(tags=["ingestion"])


@router.post(
    "/documents",
    operation_id="upsertDocuments",
    summary="Create or replace retrieval documents",
    response_model=IngestDocumentsResponse,
)
async def upsert_documents(
    payload: IngestDocumentsRequest,
    response: Response,
    caller_request_id: Annotated[
        str | None,
        Header(alias="X-Request-ID", min_length=1, max_length=128),
    ] = None,
    document_store: Annotated[DocumentStore | None, Depends(get_document_store)] = None,
) -> IngestDocumentsResponse:
    if document_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Persistent document storage is not configured.",
        )

    request_id = caller_request_id or str(uuid4())
    response.headers["X-Request-ID"] = request_id
    upserted = await document_store.upsert_documents(payload.documents)
    return IngestDocumentsResponse(upserted=upserted)
