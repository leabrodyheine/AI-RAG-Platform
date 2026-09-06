import re

from rag_observability.context import (
    MAX_REQUEST_ID_LENGTH,
    bind_request_id,
    current_request_id,
    new_request_id,
    resolve_request_id,
)

_UUID = re.compile(r"\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")


def test_new_request_id_is_a_uuid() -> None:
    assert _UUID.match(new_request_id())


def test_bind_and_read_request_id() -> None:
    bind_request_id("req-42")
    assert current_request_id() == "req-42"


def test_resolve_reuses_a_plausible_inbound_id() -> None:
    assert resolve_request_id("  browser-abc  ") == "browser-abc"


def test_resolve_mints_a_new_id_when_absent_or_implausible() -> None:
    assert _UUID.match(resolve_request_id(None))
    assert _UUID.match(resolve_request_id(""))
    assert _UUID.match(resolve_request_id("x" * (MAX_REQUEST_ID_LENGTH + 1)))
