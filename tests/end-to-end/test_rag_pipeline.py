"""End-to-end tests for the full RAG request path.

These drive the real browser -> gateway -> agent -> retrieval -> inference chain
over in-process ASGI transports (no network, no Postgres, no Redis) and cover the
behaviours a reviewer checks by hand: ingesting a document makes new evidence
retrievable, the grounded answer cites that evidence, a repeated query is served
from the retrieval cache instead of re-searching, and an upstream outage degrades
to a bounded error rather than a hang or a 500.

Pgvector search and Redis serialisation have their own unit tests under
``services/retrieval/tests``. Here the document store and cache are small
in-memory fakes wired in through FastAPI dependency overrides, so the assertions
are about how the four services compose.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

import httpx
import pytest
from agent_service.clients.inference import InferenceClient
from agent_service.clients.retrieval import RetrievalClient
from agent_service.dependencies import get_inference_client, get_retrieval_client
from agent_service.main import app as agent_app
from api_gateway.clients.agent import AgentClient
from api_gateway.dependencies import get_agent_client
from api_gateway.main import app as gateway_app
from inference_service.backends import DeterministicBackend, InferenceBackendUnavailableError
from inference_service.dependencies import get_backend
from inference_service.main import app as inference_app
from retrieval_service.cache import CacheLookup, cache_key
from retrieval_service.corpus import EvaluationDocument
from retrieval_service.dependencies import get_document_store, get_retrieval_cache
from retrieval_service.main import app as retrieval_app
from retrieval_service.search import RankedDocument, search_documents

MODEL = "deterministic-grounded-v1"
QUESTION = "What was the p95 latency in the March load test?"
LOAD_TEST_DOC = {
    "id": "march-load-test",
    "title": "March load test p95 latency",
    "source": "evaluation/performance/march-load-test.json",
    "content": (
        "The March load test measured a p95 latency of 512 milliseconds at 30 "
        "requests per second."
    ),
    "tags": ["performance", "latency", "p95"],
}
NO_EVIDENCE_ANSWER = "The retrieved evidence does not support an answer to this question."


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeDocumentStore:
    """In-memory stand-in for the pgvector-backed store.

    ``search`` reuses the production keyword ranker so relevance scores and
    ordering match what the real service would return for these tiny inputs.
    """

    embedding_version = "fake-e2e-v1"

    def __init__(self) -> None:
        self._documents: dict[str, EvaluationDocument] = {}
        self._generation = 1
        self.search_calls = 0

    async def upsert_documents(self, documents: Sequence[object]) -> int:
        for document in documents:
            self._documents[document.id] = EvaluationDocument(
                id=document.id,
                title=document.title,
                source=document.source,
                content=document.content,
                tags=tuple(document.tags),
            )
        self._generation += 1
        return len(documents)

    async def corpus_generation(self) -> int:
        return self._generation

    async def search(self, query: str, top_k: int) -> list[RankedDocument]:
        self.search_calls += 1
        return search_documents(query, top_k, tuple(self._documents.values()))


class FakeRetrievalCache:
    """Counts lookups so a test can prove a repeat query skipped the store.

    Redis wire-serialisation is covered in
    ``services/retrieval/tests/test_cache.py``; this keeps ``RankedDocument``
    objects in a dict keyed exactly as the real cache keys them.
    """

    def __init__(self) -> None:
        self._entries: dict[str, list[RankedDocument]] = {}
        self.hits = 0
        self.misses = 0

    async def lookup(
        self,
        query: str,
        top_k: int,
        embedding_version: str,
        corpus_generation: int,
    ) -> CacheLookup:
        key = cache_key(query, top_k, embedding_version, corpus_generation)
        cached = self._entries.get(key)
        if cached is None:
            self.misses += 1
            return CacheLookup(status="MISS")
        self.hits += 1
        return CacheLookup(status="HIT", results=list(cached))

    async def store(
        self,
        query: str,
        top_k: int,
        embedding_version: str,
        corpus_generation: int,
        results: list[RankedDocument],
    ) -> bool:
        key = cache_key(query, top_k, embedding_version, corpus_generation)
        self._entries[key] = list(results)
        return True


@dataclass
class Pipeline:
    browser: httpx.AsyncClient
    retrieval: httpx.AsyncClient
    store: FakeDocumentStore | None
    cache: FakeRetrievalCache | None


@contextlib.asynccontextmanager
async def build_pipeline(
    *,
    backend: object | None = None,
    document_store: FakeDocumentStore | None = None,
    retrieval_cache: FakeRetrievalCache | None = None,
    retrieval_client: RetrievalClient | None = None,
) -> AsyncIterator[Pipeline]:
    """Wire the four apps together over ASGI transports and yield the browser end."""
    backend = backend or DeterministicBackend(model=MODEL)
    inference_app.dependency_overrides[get_backend] = lambda: backend
    if document_store is not None:
        retrieval_app.dependency_overrides[get_document_store] = lambda: document_store
    if retrieval_cache is not None:
        retrieval_app.dependency_overrides[get_retrieval_cache] = lambda: retrieval_cache

    async with contextlib.AsyncExitStack() as stack:
        retrieval_http = await stack.enter_async_context(
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=retrieval_app),
                base_url="http://retrieval",
            )
        )
        inference_http = await stack.enter_async_context(
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=inference_app),
                base_url="http://inference",
            )
        )
        agent_app.dependency_overrides[get_retrieval_client] = (
            lambda: retrieval_client or RetrievalClient(retrieval_http)
        )
        agent_app.dependency_overrides[get_inference_client] = lambda: InferenceClient(
            inference_http
        )
        agent_http = await stack.enter_async_context(
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=agent_app),
                base_url="http://agent",
            )
        )
        gateway_app.dependency_overrides[get_agent_client] = lambda: AgentClient(agent_http)
        browser = await stack.enter_async_context(
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=gateway_app),
                base_url="http://gateway",
            )
        )
        try:
            yield Pipeline(
                browser=browser,
                retrieval=retrieval_http,
                store=document_store,
                cache=retrieval_cache,
            )
        finally:
            gateway_app.dependency_overrides.clear()
            agent_app.dependency_overrides.clear()
            retrieval_app.dependency_overrides.clear()
            inference_app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_ingestion_makes_new_evidence_retrievable_and_grounds_the_answer() -> None:
    store = FakeDocumentStore()
    async with build_pipeline(document_store=store) as pipe:
        # Nothing in the corpus answers the question yet: the workflow still
        # returns a bounded, source-free answer rather than guessing.
        cold = await pipe.browser.post("/chat", json={"question": QUESTION})
        assert cold.status_code == 200
        cold_body = cold.json()
        assert cold_body["citations"] == []
        assert cold_body["content"] == NO_EVIDENCE_ANSWER

        ingest = await pipe.retrieval.post(
            "/documents",
            json={"documents": [LOAD_TEST_DOC]},
            headers={"X-Request-ID": "e2e-ingest-1"},
        )
        assert ingest.status_code == 200
        assert ingest.json() == {"upserted": 1}
        assert ingest.headers["X-Request-ID"] == "e2e-ingest-1"

        warm = await pipe.browser.post(
            "/chat",
            json={"question": QUESTION},
            headers={"X-Request-ID": "e2e-chat-1"},
        )

    assert warm.status_code == 200
    assert warm.headers["X-Request-ID"] == "e2e-chat-1"
    body = warm.json()
    assert [step["label"] for step in body["trace"]] == [
        "Plan",
        "Retrieve",
        "Assess evidence",
        "Generate",
    ]
    citation = body["citations"][0]
    assert citation["id"] == "march-load-test"
    assert citation["source"] == "evaluation/performance/march-load-test.json"
    assert "512 milliseconds" in citation["excerpt"]
    assert 0.0 <= citation["relevance"] <= 1.0
    assert body["content"].startswith("Based on the retrieved evidence,")
    assert "512 milliseconds" in body["content"]
    assert body["content"].rstrip().endswith("[1]")


@pytest.mark.anyio
async def test_repeated_query_is_served_from_the_retrieval_cache() -> None:
    store = FakeDocumentStore()
    cache = FakeRetrievalCache()
    async with build_pipeline(document_store=store, retrieval_cache=cache) as pipe:
        await pipe.retrieval.post("/documents", json={"documents": [LOAD_TEST_DOC]})

        # Two identical direct searches: the X-Cache header flips MISS -> HIT and
        # the second one is answered without touching the store.
        search_body = {"query": "march load test p95 latency", "topK": 3}
        first = await pipe.retrieval.post("/search", json=search_body)
        second = await pipe.retrieval.post("/search", json=search_body)
        assert first.headers["X-Cache"] == "MISS"
        assert second.headers["X-Cache"] == "HIT"
        assert first.json() == second.json()
        searches_after_direct = store.search_calls
        assert searches_after_direct == 1

        # The same repeat behaviour holds through the full chat path.
        one = await pipe.browser.post("/chat", json={"question": QUESTION})
        two = await pipe.browser.post("/chat", json={"question": QUESTION})

    assert one.status_code == two.status_code == 200
    assert one.json()["content"] == two.json()["content"]
    assert one.json()["citations"][0]["id"] == "march-load-test"
    # One direct miss + one chat miss populated the cache; the repeats were hits.
    assert cache.misses == 2
    assert cache.hits == 2
    assert store.search_calls == searches_after_direct + 1


@pytest.mark.anyio
async def test_inference_outage_degrades_to_a_bounded_gateway_error() -> None:
    class OutageBackend:
        name = "deterministic"
        model = MODEL

        async def generate(self, prompt: str, *, max_tokens: int, temperature: float) -> None:
            raise InferenceBackendUnavailableError("simulated outage")

        async def ready(self) -> bool:
            return False

        async def aclose(self) -> None:
            return None

    store = FakeDocumentStore()
    async with build_pipeline(backend=OutageBackend(), document_store=store) as pipe:
        await pipe.retrieval.post("/documents", json={"documents": [LOAD_TEST_DOC]})
        response = await pipe.browser.post(
            "/chat",
            json={"question": QUESTION},
            headers={"X-Request-ID": "e2e-outage-1"},
        )

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "agent_unavailable"
    assert body["requestId"] == "e2e-outage-1"
    assert response.headers["X-Request-ID"] == "e2e-outage-1"


@pytest.mark.anyio
async def test_retrieval_timeout_degrades_to_a_gateway_timeout() -> None:
    def time_out(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated slow retrieval", request=request)

    timing_out_client = RetrievalClient(
        httpx.AsyncClient(
            transport=httpx.MockTransport(time_out),
            base_url="http://retrieval",
        )
    )
    async with build_pipeline(retrieval_client=timing_out_client) as pipe:
        response = await pipe.browser.post(
            "/chat",
            json={"question": QUESTION},
            headers={"X-Request-ID": "e2e-timeout-1"},
        )
        await timing_out_client.aclose()

    assert response.status_code == 504
    body = response.json()
    assert body["code"] == "agent_timeout"
    assert body["requestId"] == "e2e-timeout-1"
