import io
import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from rag_observability.instrumentation import instrument_app
from rag_observability.logging import configure_logging


@pytest.fixture
def app_client(tmp_path):
    app = FastAPI()

    @app.get("/echo/{name}")
    async def echo(name: str) -> dict[str, str]:
        logging.getLogger("unit.handler").info("handling", extra={"echo_name": name})
        return {"name": name}

    @app.get("/boom")
    async def boom() -> dict[str, str]:
        raise RuntimeError("kaboom")

    instrument_app(app, "unit-service")
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_request_id_is_echoed_and_minted_when_absent(app_client) -> None:
    response = app_client.get("/echo/a")
    assert response.status_code == 200
    assert response.headers["X-Request-ID"]


def test_caller_request_id_is_preserved(app_client) -> None:
    response = app_client.get("/echo/a", headers={"X-Request-ID": "caller-123"})
    assert response.headers["X-Request-ID"] == "caller-123"


def test_metrics_endpoint_reports_served_requests(app_client) -> None:
    app_client.get("/echo/a")

    body = app_client.get("/metrics").text
    assert "http_server_requests_total" in body
    assert 'route="/echo/{name}"' in body
    assert 'service="unit-service"' in body


def test_metrics_and_health_are_not_counted(app_client) -> None:
    app_client.get("/metrics")
    body = app_client.get("/metrics").text
    assert 'route="/metrics"' not in body


def test_failing_request_is_counted_as_5xx(app_client) -> None:
    assert app_client.get("/boom").status_code == 500
    body = app_client.get("/metrics").text
    assert 'status="5xx"' in body


def test_access_log_line_is_structured_json_with_trace_id() -> None:
    stream = io.StringIO()
    configure_logging("log-service", stream=stream)

    app = FastAPI()

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"pong": "1"}

    instrument_app(app, "log-service")
    with TestClient(app) as client:
        client.get("/ping", headers={"X-Request-ID": "trace-corr-1"})

    lines = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
    handled = [entry for entry in lines if entry["message"] == "request handled"]
    assert handled, stream.getvalue()
    entry = handled[-1]
    assert entry["route"] == "/ping"
    assert entry["status"] == 200
    assert entry["request_id"] == "trace-corr-1"
    assert len(entry["trace_id"]) == 32
