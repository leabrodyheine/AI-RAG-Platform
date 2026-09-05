from pydantic import BaseModel, ConfigDict, Field


def to_camel(field_name: str) -> str:
    first, *rest = field_name.split("_")
    return first + "".join(part.capitalize() for part in rest)


class ContractModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
    )


class SearchRequest(ContractModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=3, ge=1, le=10)


class SearchResult(ContractModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)
    relevance: float = Field(ge=0, le=1)


class SearchResponse(ContractModel):
    results: list[SearchResult]
