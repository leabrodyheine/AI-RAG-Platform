"""Replay a dataset through the real agent workflow, in-process.

The harness wires the production :func:`agent_service.workflow.run_workflow` to
the retrieval service's in-memory keyword search and the deterministic
inference backend. No database, Redis, model download, GPU, or running service
is involved, so a full run is reproducible from a clean checkout.

For each case it captures the answer, the citations the workflow kept, every
document id retrieval returned (across the rewrite too), the trace labels, and
a separate clean single-pass retrieval used for the IR metrics, then scores it
with :mod:`evaluation.quality.metrics`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from agent_service.clients.inference import GeneratedAnswer
from agent_service.schemas import Citation
from agent_service.workflow import WorkflowConfig, run_workflow
from inference_service.backends import DeterministicBackend
from retrieval_service.corpus import EVALUATION_DOCUMENTS
from retrieval_service.search import search_documents

from evaluation.quality.judge import AnswerJudge, KeywordJudge
from evaluation.quality.metrics import CaseResult, QualityMetrics, aggregate_metrics, evaluate_case
from evaluation.quality.schema import EvaluationCase, EvaluationDataset

RETRIEVAL_MODE = "in-memory-keyword"
DEFAULT_INFERENCE_MODEL = "deterministic-grounded-v1"
DEFAULT_TOP_K = 3


def _to_citation(ranked) -> Citation:
    return Citation(
        id=ranked.document.id,
        title=ranked.document.title,
        source=ranked.document.source,
        excerpt=ranked.document.content,
        relevance=ranked.relevance,
    )


class _RecordingRetriever:
    """Retrieval client backed by the deterministic keyword search.

    Mirrors the async surface of ``agent_service.clients.retrieval.RetrievalClient``
    that the workflow uses, and remembers every document id it has returned.
    """

    def __init__(self, top_k: int) -> None:
        self._top_k = top_k
        self.returned_ids: list[str] = []
        self.queries: list[str] = []

    async def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        request_id: str | None = None,
    ) -> list[Citation]:
        self.queries.append(query)
        ranked = search_documents(query, top_k or self._top_k)
        for item in ranked:
            if item.document.id not in self.returned_ids:
                self.returned_ids.append(item.document.id)
        return [_to_citation(item) for item in ranked]


class _DeterministicInference:
    """Inference client that wraps the deterministic backend for the workflow."""

    def __init__(self, model: str) -> None:
        self._backend = DeterministicBackend(model=model)

    async def generate(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.1,
        request_id: str | None = None,
    ) -> GeneratedAnswer:
        result = await self._backend.generate(
            prompt, max_tokens=max_tokens, temperature=temperature
        )
        return GeneratedAnswer(
            content=result.content,
            model=self._backend.model,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
        )


@dataclass(frozen=True)
class RunResult:
    dataset: EvaluationDataset
    results: list[CaseResult]
    metrics: QualityMetrics
    top_k: int
    workflow_config: WorkflowConfig
    judge_name: str
    inference_model: str
    corpus_size: int
    retrieval_mode: str = RETRIEVAL_MODE
    inference_backend: str = DeterministicBackend.name


async def _evaluate_one(
    case: EvaluationCase,
    *,
    top_k: int,
    workflow_config: WorkflowConfig,
    inference_model: str,
    judge: AnswerJudge,
) -> CaseResult:
    retriever = _RecordingRetriever(top_k)
    inference = _DeterministicInference(inference_model)
    outcome = await run_workflow(
        case.question,
        retrieval_client=retriever,  # type: ignore[arg-type]
        inference_client=inference,  # type: ignore[arg-type]
        config=workflow_config,
        request_id=f"eval-{case.id}",
    )
    ranked_retrieval = tuple(
        item.document.id for item in search_documents(case.question, top_k)
    )
    return evaluate_case(
        case,
        answer=outcome.content,
        ranked_retrieval=ranked_retrieval,
        workflow_retrieved=tuple(retriever.returned_ids),
        cited=tuple(citation.id for citation in outcome.citations),
        trace=tuple(step.label for step in outcome.trace),
        judge=judge,
    )


async def _evaluate_all(
    dataset: EvaluationDataset,
    *,
    top_k: int,
    workflow_config: WorkflowConfig,
    inference_model: str,
    judge: AnswerJudge,
) -> list[CaseResult]:
    results: list[CaseResult] = []
    for case in dataset.cases:
        results.append(
            await _evaluate_one(
                case,
                top_k=top_k,
                workflow_config=workflow_config,
                inference_model=inference_model,
                judge=judge,
            )
        )
    return results


def run_evaluation(
    dataset: EvaluationDataset,
    *,
    judge: AnswerJudge | None = None,
    judge_name: str = "keyword",
    top_k: int = DEFAULT_TOP_K,
    workflow_config: WorkflowConfig | None = None,
    inference_model: str = DEFAULT_INFERENCE_MODEL,
) -> RunResult:
    """Replay every case in ``dataset`` and return scored results plus metrics."""
    active_judge = judge or KeywordJudge()
    config = workflow_config or WorkflowConfig()
    results = asyncio.run(
        _evaluate_all(
            dataset,
            top_k=top_k,
            workflow_config=config,
            inference_model=inference_model,
            judge=active_judge,
        )
    )
    return RunResult(
        dataset=dataset,
        results=results,
        metrics=aggregate_metrics(results),
        top_k=top_k,
        workflow_config=config,
        judge_name=judge_name if judge is None else getattr(active_judge, "name", judge_name),
        inference_model=inference_model,
        corpus_size=len(EVALUATION_DOCUMENTS),
    )
