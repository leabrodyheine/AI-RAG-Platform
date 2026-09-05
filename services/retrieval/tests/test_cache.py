from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ConnectionError
from retrieval_service.cache import RetrievalCache, cache_key
from retrieval_service.corpus import EvaluationDocument
from retrieval_service.search import RankedDocument


def ranked_result() -> RankedDocument:
    return RankedDocument(
        document=EvaluationDocument(
            id="result-1",
            title="Result one",
            source="evaluation/result-1.json",
            content="Retrieval latency was reduced.",
            tags=("retrieval",),
        ),
        relevance=0.875,
    )


def test_cache_keys_normalize_queries_and_include_all_ranking_inputs() -> None:
    base = cache_key(" Retrieval   LATENCY ", 3, "model-v1", 4)

    assert base == cache_key("retrieval latency", 3, "model-v1", 4)
    assert base != cache_key("retrieval latency", 2, "model-v1", 4)
    assert base != cache_key("retrieval latency", 3, "model-v2", 4)
    assert base != cache_key("retrieval latency", 3, "model-v1", 5)
    assert "retrieval latency" not in base


@pytest.mark.anyio
async def test_cache_round_trips_ranked_results() -> None:
    client = AsyncMock()
    cache = RetrievalCache(client, ttl_seconds=90)

    await cache.store("latency", 3, "model-v1", 1, [ranked_result()])
    client.get.return_value = client.set.await_args.args[1]
    lookup = await cache.lookup("latency", 3, "model-v1", 1)

    assert lookup.status == "HIT"
    assert lookup.results is not None
    assert lookup.results[0].document.id == "result-1"
    assert lookup.results[0].relevance == 0.875
    client.set.assert_awaited_once_with(
        cache_key("latency", 3, "model-v1", 1),
        client.set.await_args.args[1],
        ex=90,
    )


@pytest.mark.anyio
async def test_cache_distinguishes_an_empty_hit_from_a_miss() -> None:
    client = AsyncMock()
    cache = RetrievalCache(client, ttl_seconds=60)
    client.get.side_effect = ["[]", None]

    hit = await cache.lookup("nothing", 3, "model-v1", 1)
    miss = await cache.lookup("missing", 3, "model-v1", 1)

    assert hit == type(hit)(status="HIT", results=[])
    assert miss == type(miss)(status="MISS")


@pytest.mark.anyio
async def test_cache_deletes_malformed_entries_and_treats_them_as_misses() -> None:
    client = AsyncMock()
    client.get.return_value = '{"not":"a result list"}'
    cache = RetrievalCache(client, ttl_seconds=60)

    lookup = await cache.lookup("latency", 3, "model-v1", 1)

    assert lookup.status == "MISS"
    client.delete.assert_awaited_once_with(cache_key("latency", 3, "model-v1", 1))


@pytest.mark.anyio
async def test_cache_fails_open_when_redis_is_unavailable() -> None:
    client = AsyncMock()
    client.get.side_effect = ConnectionError("offline")
    client.set.side_effect = ConnectionError("offline")
    cache = RetrievalCache(client, ttl_seconds=60)

    lookup = await cache.lookup("latency", 3, "model-v1", 1)
    await cache.store("latency", 3, "model-v1", 1, [ranked_result()])

    assert lookup.status == "BYPASS"


@pytest.mark.anyio
async def test_cache_closes_its_client() -> None:
    client = AsyncMock()
    cache = RetrievalCache(client, ttl_seconds=60)

    await cache.close()

    client.aclose.assert_awaited_once()
