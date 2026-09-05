import json
from pathlib import Path

CONTRACT_PATH = (
    Path(__file__).parents[2] / "contracts" / "openapi" / "chat-v1.openapi.json"
)


def load_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text())


def test_chat_contract_defines_the_public_endpoint() -> None:
    contract = load_contract()

    assert contract["openapi"] == "3.1.0"
    assert contract["info"]["version"] == "1.0.0"
    assert contract["paths"]["/chat"]["post"]["operationId"] == "createChatAnswer"


def test_question_validation_limits_are_explicit() -> None:
    question = load_contract()["components"]["schemas"]["ChatRequest"]["properties"][
        "question"
    ]

    assert question["minLength"] == 1
    assert question["maxLength"] == 4000


def test_success_response_matches_the_frontend_contract() -> None:
    contract = load_contract()
    response_schema = contract["components"]["schemas"]["ChatResponse"]

    assert response_schema["additionalProperties"] is False
    assert set(response_schema["required"]) == {
        "content",
        "citations",
        "trace",
        "totalDurationMs",
    }
    assert set(contract["components"]["schemas"]["Citation"]["required"]) == {
        "id",
        "title",
        "source",
        "excerpt",
        "relevance",
    }
    assert set(contract["components"]["schemas"]["TraceStep"]["required"]) == {
        "label",
        "detail",
        "durationMs",
    }


def test_endpoint_documents_request_ids_and_expected_errors() -> None:
    contract = load_contract()
    operation = contract["paths"]["/chat"]["post"]

    assert operation["parameters"] == [{"$ref": "#/components/parameters/RequestId"}]
    assert set(operation["responses"]) == {"200", "422", "503", "504"}
    for response in operation["responses"].values():
        if "$ref" in response:
            response_name = response["$ref"].rsplit("/", maxsplit=1)[-1]
            response = contract["components"]["responses"][response_name]
        assert "X-Request-ID" in response["headers"]
