from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class DocumentInput(ContractModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    source: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=20_000)
    tags: tuple[str, ...] = Field(default=(), max_length=20)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, tags: tuple[str, ...]) -> tuple[str, ...]:
        if any(not tag or len(tag) > 64 for tag in tags):
            raise ValueError("tags must contain strings from 1 through 64 characters")
        if len(set(tags)) != len(tags):
            raise ValueError("tags must be unique")
        return tags


class IngestDocumentsRequest(ContractModel):
    documents: list[DocumentInput] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_document_ids(self) -> "IngestDocumentsRequest":
        document_ids = [document.id for document in self.documents]
        if len(set(document_ids)) != len(document_ids):
            raise ValueError("document ids must be unique within a request")
        return self


class IngestDocumentsResponse(ContractModel):
    upserted: int = Field(ge=1, le=100)
