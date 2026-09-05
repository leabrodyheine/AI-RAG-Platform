import json
from pathlib import Path

CONTRACT_PATH = (
    Path(__file__).parents[2] / "contracts" / "openapi" / "inference-v1.openapi.json"
)


def load_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text())


def test_inference_contract_defines_generation_endpoint() -> None:
    contract = load_contract()

    assert contract["openapi"] == "3.1.0"
    assert contract["info"]["version"] == "1.0.0"
    assert contract["paths"]["/generate"]["post"]["operationId"] == "generateText"


def test_inference_contract_bounds_generation_inputs() -> None:
    request = load_contract()["components"]["schemas"]["GenerationRequest"]

    assert request["additionalProperties"] is False
    assert set(request["required"]) == {"prompt", "maxTokens", "temperature"}
    assert request["properties"]["prompt"]["maxLength"] == 20_000
    assert request["properties"]["maxTokens"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 2048,
    }
    assert request["properties"]["temperature"] == {
        "type": "number",
        "minimum": 0,
        "maximum": 2,
    }


def test_inference_response_reports_model_and_usage() -> None:
    schemas = load_contract()["components"]["schemas"]

    assert set(schemas["GenerationResponse"]["required"]) == {"content", "model", "usage"}
    assert set(schemas["TokenUsage"]["required"]) == {
        "promptTokens",
        "completionTokens",
    }


def test_inference_contract_documents_request_ids_and_failures() -> None:
    contract = load_contract()
    operation = contract["paths"]["/generate"]["post"]

    assert operation["parameters"] == [{"$ref": "#/components/parameters/RequestId"}]
    assert set(operation["responses"]) == {"200", "422", "503", "504"}
    for response in operation["responses"].values():
        assert "X-Request-ID" in response["headers"]
