"""Locust load driver for the RAG chat path.

Run it against a running stack (the Compose stack, or the local fallback stack
started by ``scripts/run_local_stack.py``)::

    locust -f load-tests/locustfile.py --host http://localhost:8000 \
        --headless --users 16 --spawn-rate 4 --run-time 60s

The scenario files in ``load-tests/scenarios/`` hold the user count, spawn rate,
and run time for each named profile; ``evaluation.performance.run`` reads them
and invokes Locust with these flags.

Environment:
  LOAD_QUESTION_SET  path to a question set (default: the tracked core set)
  LOAD_WAIT_MIN      per-user think time lower bound, seconds (default 0.5)
  LOAD_WAIT_MAX      per-user think time upper bound, seconds (default 2.0)
"""

from __future__ import annotations

import json
import os
import random
import uuid
from pathlib import Path

from locust import HttpUser, between, task

_DEFAULT_QUESTION_SET = Path(__file__).parent / "dataset" / "questions.json"


def _load_questions() -> list[dict[str, str]]:
    path = Path(os.getenv("LOAD_QUESTION_SET", str(_DEFAULT_QUESTION_SET)))
    payload = json.loads(path.read_text(encoding="utf-8"))
    questions = payload["questions"] if isinstance(payload, dict) else payload
    if not questions:
        raise ValueError(f"question set {path} contains no questions")
    return questions


def _wait_bounds() -> tuple[float, float]:
    low = float(os.getenv("LOAD_WAIT_MIN", "0.5"))
    high = float(os.getenv("LOAD_WAIT_MAX", "2.0"))
    if low < 0 or high < low:
        raise ValueError("LOAD_WAIT_MIN/LOAD_WAIT_MAX must satisfy 0 <= min <= max")
    return low, high


QUESTIONS = _load_questions()
_WAIT_MIN, _WAIT_MAX = _wait_bounds()


class ChatUser(HttpUser):
    """A browser client asking the gateway one chat question at a time."""

    wait_time = between(_WAIT_MIN, _WAIT_MAX)

    @task
    def ask(self) -> None:
        question = random.choice(QUESTIONS)
        request_id = f"load-{uuid.uuid4()}"
        # Group results by question kind so the report can separate the
        # direct-answer path from the retrieval + generation path.
        name = f"/chat [{question.get('kind', 'unknown')}]"
        with self.client.post(
            "/chat",
            json={"question": question["question"]},
            headers={"X-Request-ID": request_id, "Content-Type": "application/json"},
            name=name,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"status {response.status_code}")
                return
            body = response.json()
            if not body.get("content"):
                response.failure("empty answer content")
                return
            response.success()
