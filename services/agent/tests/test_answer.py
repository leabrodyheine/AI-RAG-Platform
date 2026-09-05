import pytest
from agent_service.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_answer_returns_a_contract_compatible_development_response() -> None:
    response = client.post(
        "/answer",
        json={"question": "What is driving p95 latency?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"content", "citations", "trace", "totalDurationMs"}
    assert isinstance(body["content"], str)
    assert body["content"]
    assert body["content"].startswith("The development agent classified this as a performance")
    assert body["citations"] == []
    assert len(body["trace"]) == 1
    assert set(body["trace"][0]) == {"label", "detail", "durationMs"}
    assert body["trace"][0]["label"] == "Agent"
    assert body["trace"][0]["detail"] == (
        "Performance question routed to the development workflow"
    )
    assert isinstance(body["trace"][0]["durationMs"], int)
    assert body["trace"][0]["durationMs"] >= 0
    assert isinstance(body["totalDurationMs"], int)
    assert body["totalDurationMs"] >= 0
    assert body["totalDurationMs"] == body["trace"][0]["durationMs"]


@pytest.mark.parametrize(
    ("question", "expected_content", "expected_trace"),
    [
        (
            "Why is model performance slow?",
            "performance investigation",
            "Performance question routed to the development workflow",
        ),
        (
            "Compare retrieval cache behavior",
            "retrieval investigation",
            "Retrieval question routed to the development workflow",
        ),
        (
            "Summarize the latest run",
            "received the question successfully",
            "General question routed to the development workflow",
        ),
    ],
)
def test_answer_routes_supported_question_categories(
    question: str,
    expected_content: str,
    expected_trace: str,
) -> None:
    response = client.post("/answer", json={"question": question})

    assert response.status_code == 200
    assert expected_content in response.json()["content"]
    assert response.json()["trace"][0]["detail"] == expected_trace


def test_answer_strips_surrounding_question_whitespace() -> None:
    response = client.post("/answer", json={"question": "  CACHE behavior\n"})

    assert response.status_code == 200
    assert "retrieval investigation" in response.json()["content"]


@pytest.mark.parametrize("question", ["", "   \n\t"])
def test_answer_rejects_empty_questions(question: str) -> None:
    response = client.post("/answer", json={"question": question})

    assert response.status_code == 422


def test_answer_accepts_the_question_length_limit() -> None:
    response = client.post("/answer", json={"question": "a" * 4000})

    assert response.status_code == 200


def test_answer_rejects_questions_over_the_length_limit() -> None:
    response = client.post("/answer", json={"question": "a" * 4001})

    assert response.status_code == 422


def test_answer_rejects_unknown_request_fields() -> None:
    response = client.post(
        "/answer",
        json={"question": "Summarize the run", "unexpected": True},
    )

    assert response.status_code == 422
