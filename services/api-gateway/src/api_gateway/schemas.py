from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ErrorCode = Literal["validation_error", "agent_unavailable", "agent_timeout"]


def to_camel(field_name: str) -> str:
    first, *rest = field_name.split("_")
    return first + "".join(part.capitalize() for part in rest)


class ContractModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
    )


class ChatRequest(ContractModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=4000)


class Citation(ContractModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)
    relevance: float = Field(ge=0, le=1)


class TraceStep(ContractModel):
    label: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    duration_ms: int = Field(ge=0)


class ChatResponse(ContractModel):
    content: str = Field(min_length=1)
    citations: list[Citation]
    trace: list[TraceStep]
    total_duration_ms: int = Field(ge=0)


class ErrorResponse(ContractModel):
    code: ErrorCode
    message: str = Field(min_length=1)
    request_id: str = Field(min_length=1, max_length=128)
