"""One JSON object per log line, with the fields every service shares.

``configure_logging`` installs a single stderr handler on the root logger whose
formatter always emits ``timestamp``, ``level``, ``logger``, ``message``, and
``service``, and adds ``request_id`` / ``trace_id`` / ``span_id`` whenever a
request is in scope. Anything passed through ``logging``'s ``extra=`` is merged
in, so ``logger.info("...", extra={"route": "/chat"})`` just works.
"""

import json
import logging
import os
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from rag_observability.context import current_request_id, current_service
from rag_observability.tracing import current_trace_ids

_RESERVED = frozenset(
    vars(logging.makeLogRecord({})).keys()
    | {"message", "asctime", "taskName"}
)

_configured = False
_service_name = "unknown"


class JsonLogFormatter(logging.Formatter):
    """Render a log record as a compact single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "service": getattr(record, "service", None) or current_service() or _service_name,
            "message": record.getMessage(),
        }

        request_id = current_request_id()
        if request_id is not None:
            payload["request_id"] = request_id
        trace_id, span_id = current_trace_ids()
        if trace_id is not None:
            payload["trace_id"] = trace_id
            payload["span_id"] = span_id

        for key, value in record.__dict__.items():
            if key not in _RESERVED and key != "service":
                payload[key] = _safe(value)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, separators=(",", ":"), default=_safe)


def _safe(value: Any) -> Any:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_safe(item) for item in value]
    return repr(value)


def configure_logging(
    service_name: str,
    *,
    level: str | int | None = None,
    stream: Any | None = None,
) -> None:
    """Install the JSON formatter on the root logger for ``service_name``.

    Idempotent: repeated calls only update the recorded service name and level,
    so importing several service apps into one test process is safe.
    """
    global _configured, _service_name
    _service_name = service_name

    resolved_level = level if level is not None else os.getenv("LOG_LEVEL", "INFO")
    root = logging.getLogger()
    root.setLevel(resolved_level)

    if not _configured:
        handler = logging.StreamHandler(stream or sys.stderr)
        handler.setFormatter(JsonLogFormatter())
        root.handlers = [handler]
        logging.captureWarnings(True)
        _configured = True
    else:
        for handler in root.handlers:
            handler.setFormatter(JsonLogFormatter())
