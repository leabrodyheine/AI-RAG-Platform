import logging

import pytest
from rag_observability.context import bind_request_id


@pytest.fixture(autouse=True)
def _restore_root_logger():
    """Snapshot and restore root logger state around each test.

    ``configure_logging`` deliberately takes over the root logger's handlers, so
    tests that call it must not leak that into pytest's own log capture.
    """
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    try:
        yield
    finally:
        root.handlers = saved_handlers
        root.setLevel(saved_level)


@pytest.fixture(autouse=True)
def _clear_request_id():
    bind_request_id(None)  # type: ignore[arg-type]
    yield
    bind_request_id(None)  # type: ignore[arg-type]
