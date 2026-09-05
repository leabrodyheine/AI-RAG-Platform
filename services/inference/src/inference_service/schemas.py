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


class GenerationRequest(ContractModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    prompt: str = Field(min_length=1, max_length=20_000)
    max_tokens: int = Field(ge=1, le=2048)
    temperature: float = Field(ge=0, le=2)


class TokenUsage(ContractModel):
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)


class GenerationResponse(ContractModel):
    content: str = Field(min_length=1)
    model: str = Field(min_length=1)
    usage: TokenUsage
