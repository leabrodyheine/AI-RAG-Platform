"""Deterministic search that can later be replaced by hybrid vector retrieval."""

import re
from dataclasses import dataclass

from retrieval_service.corpus import EVALUATION_DOCUMENTS, EvaluationDocument

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "does",
    "for",
    "in",
    "is",
    "of",
    "on",
    "the",
    "to",
    "what",
}


@dataclass(frozen=True)
class RankedDocument:
    document: EvaluationDocument
    relevance: float


def search_documents(query: str, top_k: int = 3) -> list[RankedDocument]:
    query_terms = _tokenize(query)
    if not query_terms:
        return []

    ranked: list[RankedDocument] = []
    for document in EVALUATION_DOCUMENTS:
        title_terms = _tokenize(document.title)
        tag_terms = set(document.tags)
        content_terms = _tokenize(document.content)
        matched_terms = query_terms & (title_terms | tag_terms | content_terms)
        if not matched_terms:
            continue

        weighted_matches = sum(
            2 if term in title_terms or term in tag_terms else 1 for term in matched_terms
        )
        relevance = min(weighted_matches / (2 * len(query_terms)), 1.0)
        ranked.append(RankedDocument(document=document, relevance=round(relevance, 4)))

    ranked.sort(key=lambda result: (-result.relevance, result.document.id))
    return ranked[:top_k]


def _tokenize(text: str) -> set[str]:
    return {token for token in TOKEN_PATTERN.findall(text.casefold()) if token not in STOP_WORDS}
