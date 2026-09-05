from pydantic import BaseModel, ConfigDict, Field


def to_camel(field_name: str) -> str:
    first, *rest = field_name.split("_")
    return first + "".join(part.capitalize() for part in rest)


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResponseModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
    )


class ChatRequest(RequestModel):
    question: str = Field(min_length=1, max_length=4000)


class Citation(ResponseModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)
    relevance: float = Field(ge=0, le=1)


class TraceStep(ResponseModel):
    label: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    duration_ms: int = Field(ge=0)


class ChatResponse(ResponseModel):
    content: str = Field(min_length=1)
    citations: list[Citation]
    trace: list[TraceStep]
    total_duration_ms: int = Field(ge=0)
