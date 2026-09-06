import io
import json
import logging

from rag_observability.context import bind_request_id, bind_service
from rag_observability.logging import JsonLogFormatter, configure_logging


def _record(msg: str = "hello %s", args: tuple = ("world",), **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_formatter_emits_single_line_json_with_core_fields() -> None:
    line = JsonLogFormatter().format(_record(service="agent"))

    assert "\n" not in line
    payload = json.loads(line)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.logger"
    assert payload["service"] == "agent"
    assert payload["message"] == "hello world"
    assert "timestamp" in payload


def test_formatter_includes_request_id_when_bound() -> None:
    bind_request_id("req-logging-1")

    payload = json.loads(JsonLogFormatter().format(_record()))

    assert payload["request_id"] == "req-logging-1"


def test_bound_service_wins_over_the_module_default() -> None:
    configure_logging("module-default")
    bind_service("retrieval")

    payload = json.loads(JsonLogFormatter().format(_record()))

    assert payload["service"] == "retrieval"


def test_formatter_merges_extra_fields_and_stays_serialisable() -> None:
    payload = json.loads(
        JsonLogFormatter().format(_record(route="/chat", status=200, obj=object()))
    )

    assert payload["route"] == "/chat"
    assert payload["status"] == 200
    assert isinstance(payload["obj"], str)


def test_configure_logging_is_idempotent_and_routes_through_json() -> None:
    stream = io.StringIO()
    configure_logging("retrieval", level="DEBUG", stream=stream)
    configure_logging("retrieval", level="DEBUG", stream=stream)

    assert len(logging.getLogger().handlers) == 1

    logging.getLogger("x").warning("something happened")

    payload = json.loads(stream.getvalue().strip().splitlines()[-1])
    assert payload["message"] == "something happened"
    assert payload["level"] == "WARNING"
    assert payload["service"] == "retrieval"
