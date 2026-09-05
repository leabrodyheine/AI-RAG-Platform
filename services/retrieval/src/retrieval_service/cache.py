import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from retrieval_service.corpus import EvaluationDocument
from retrieval_service.schemas import SearchResult
from retrieval_service.search import RankedDocument

CACHE_KEY_PREFIX = "retrieval:search"


@dataclass(frozen=True)
class CacheLookup:
    status: Literal["HIT", "MISS", "BYPASS"]
    results: list[RankedDocument] | None = None


class RetrievalCache:
    def __init__(self, client: Redis, ttl_seconds: int) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds

    @classmethod
    def from_url(cls, redis_url: str, ttl_seconds: int) -> "RetrievalCache":
        client = Redis.from_url(redis_url, decode_responses=True)
        return cls(client, ttl_seconds)

    async def lookup(
        self,
        query: str,
        top_k: int,
        embedding_version: str,
        corpus_generation: int,
    ) -> CacheLookup:
        key = cache_key(query, top_k, embedding_version, corpus_generation)
        try:
            cached_value = await self._client.get(key)
        except RedisError:
            return CacheLookup(status="BYPASS")

        if cached_value is None:
            return CacheLookup(status="MISS")

        try:
            return CacheLookup(status="HIT", results=_deserialize_results(cached_value))
        except (json.JSONDecodeError, TypeError, ValueError, ValidationError):
            try:
                await self._client.delete(key)
            except RedisError:
                pass
            return CacheLookup(status="MISS")

    async def store(
        self,
        query: str,
        top_k: int,
        embedding_version: str,
        corpus_generation: int,
        results: list[RankedDocument],
    ) -> None:
        key = cache_key(query, top_k, embedding_version, corpus_generation)
        value = _serialize_results(results)
        try:
            await self._client.set(key, value, ex=self._ttl_seconds)
        except RedisError:
            pass

    async def close(self) -> None:
        await self._client.aclose()


def cache_key(
    query: str,
    top_k: int,
    embedding_version: str,
    corpus_generation: int,
) -> str:
    normalized_query = " ".join(query.casefold().split())
    identity = "\0".join(
        (embedding_version, str(corpus_generation), str(top_k), normalized_query)
    )
    digest = hashlib.sha256(identity.encode()).hexdigest()
    return f"{CACHE_KEY_PREFIX}:{digest}"


def _serialize_results(results: list[RankedDocument]) -> str:
    payload = [
        SearchResult(
            id=result.document.id,
            title=result.document.title,
            source=result.document.source,
            excerpt=result.document.content,
            relevance=result.relevance,
        ).model_dump()
        for result in results
    ]
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _deserialize_results(cached_value: str | bytes) -> list[RankedDocument]:
    payload = json.loads(cached_value)
    if not isinstance(payload, list):
        raise ValueError("cached search results must be a list")
    results = [SearchResult.model_validate(item) for item in payload]
    return [
        RankedDocument(
            document=EvaluationDocument(
                id=result.id,
                title=result.title,
                source=result.source,
                content=result.excerpt,
                tags=(),
            ),
            relevance=result.relevance,
        )
        for result in results
    ]
