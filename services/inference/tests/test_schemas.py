import pytest
from inference_service.schemas import GenerationRequest, GenerationResponse, TokenUsage
from pydantic import ValidationError


def test_generation_request_accepts_contract_limits() -> None:
    request = GenerationRequest.model_validate(
        {"prompt": " grounded prompt ", "maxTokens": 2048, "temperature": 2}
    )

    assert request.prompt == "grounded prompt"
    assert request.max_tokens == 2048


@pytest.mark.parametrize(
    "payload",
    [
        {"prompt": "", "maxTokens": 10, "temperature": 0},
        {"prompt": "prompt", "maxTokens": 0, "temperature": 0},
        {"prompt": "prompt", "maxTokens": 2049, "temperature": 0},
        {"prompt": "prompt", "maxTokens": 10, "temperature": 2.1},
        {"prompt": "prompt", "maxTokens": 10, "temperature": 0, "extra": True},
    ],
)
def test_generation_request_rejects_invalid_payloads(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        GenerationRequest.model_validate(payload)


def test_generation_response_uses_camel_case_token_counts() -> None:
    response = GenerationResponse(
        content="Grounded answer.",
        model="test-model",
        usage=TokenUsage(prompt_tokens=12, completion_tokens=3),
    )

    assert response.model_dump(by_alias=True) == {
        "content": "Grounded answer.",
        "model": "test-model",
        "usage": {"promptTokens": 12, "completionTokens": 3},
    }
