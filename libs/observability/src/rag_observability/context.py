"""The request identifier that ties one chat request's logs and spans together.

The browser-facing gateway accepts an ``X-Request-ID`` from the caller or mints
one, and every internal service forwards the same value on its downstream calls.
Holding it in a :class:`~contextvars.ContextVar` lets the log formatter and the
tracing middleware read it without threading it through every function.
"""

from contextvars import ContextVar
from uuid import uuid4

REQUEST_ID_HEADER = "X-Request-ID"
MAX_REQUEST_ID_LENGTH = 128

_request_id: ContextVar[str | None] = ContextVar("rag_request_id", default=None)
_service: ContextVar[str | None] = ContextVar("rag_service", default=None)


def bind_service(service_name: str) -> None:
    """Record which service is handling the current context (for log fields)."""
    _service.set(service_name)


def current_service() -> str | None:
    """Return the service bound to the current context, if any."""
    return _service.get()


def new_request_id() -> str:
    """Return a fresh random request identifier."""
    return str(uuid4())


def bind_request_id(request_id: str) -> None:
    """Make ``request_id`` the identifier for the current context."""
    _request_id.set(request_id)


def current_request_id() -> str | None:
    """Return the request identifier bound to the current context, if any."""
    return _request_id.get()


def resolve_request_id(incoming: str | None) -> str:
    """Choose the request id for a request from its inbound header value.

    A caller-supplied value is reused when it is a plausible identifier (present
    and within :data:`MAX_REQUEST_ID_LENGTH`); anything else is replaced with a
    freshly minted id so downstream correlation still works.
    """
    if incoming:
        candidate = incoming.strip()
        if 0 < len(candidate) <= MAX_REQUEST_ID_LENGTH:
            return candidate
    return new_request_id()
