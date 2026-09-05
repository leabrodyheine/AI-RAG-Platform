import json
from pathlib import Path

CONTRACT_PATH = (
    Path(__file__).parents[2] / "contracts" / "openapi" / "retrieval-v1.openapi.json"
)


def load_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text())


def test_retrieval_contract_defines_the_search_endpoint() -> None:
    contract = load_contract()

    assert contract["openapi"] == "3.1.0"
    assert contract["info"]["version"] == "1.0.0"
    assert contract["paths"]["/search"]["post"]["operationId"] == "searchEvidence"


def test_retrieval_contract_defines_query_limits() -> None:
    properties = load_contract()["components"]["schemas"]["SearchRequest"]["properties"]

    assert properties["query"]["minLength"] == 1
    assert properties["query"]["maxLength"] == 4000
    assert properties["topK"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 10,
        "default": 3,
    }


def test_retrieval_results_are_citation_ready() -> None:
    result = load_contract()["components"]["schemas"]["SearchResult"]

    assert result["additionalProperties"] is False
    assert set(result["required"]) == {"id", "title", "source", "excerpt", "relevance"}


def test_retrieval_contract_documents_request_id_propagation() -> None:
    operation = load_contract()["paths"]["/search"]["post"]

    assert operation["parameters"] == [{"$ref": "#/components/parameters/RequestId"}]
    assert "X-Request-ID" in operation["responses"]["200"]["headers"]
