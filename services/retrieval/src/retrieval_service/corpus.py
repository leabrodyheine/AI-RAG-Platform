from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationDocument:
    id: str
    title: str
    source: str
    content: str
    tags: tuple[str, ...]


EVALUATION_DOCUMENTS = (
    EvaluationDocument(
        id="retrieval-benchmark-1842",
        title="Retrieval benchmark · run #1842",
        source="evaluation/performance/retrieval.json",
        content=(
            "At 32 concurrent users, cache misses increased vector-search p95 latency "
            "from 112 ms to 391 ms. Retrieval accounted for 46% of end-to-end request "
            "time on the uncached path."
        ),
        tags=("retrieval", "latency", "performance", "p95", "cache", "concurrency"),
    ),
    EvaluationDocument(
        id="cache-comparison-1842",
        title="Cache comparison · run #1842",
        source="evaluation/performance/cache-comparison.json",
        content=(
            "Cached retrieval reduced p95 latency from 391 ms to 118 ms, a 69.8% "
            "improvement. Cache coverage was 63% and answer quality remained within "
            "the evaluation margin."
        ),
        tags=("retrieval", "cache", "cached", "uncached", "latency", "quality"),
    ),
    EvaluationDocument(
        id="inference-comparison-1839",
        title="Inference backend comparison · run #1839",
        source="evaluation/performance/inference-backends.json",
        content=(
            "vLLM delivered 41 tokens per second with 286 ms time to first token. "
            "The Triton TensorRT-LLM run delivered 48 tokens per second with 241 ms "
            "time to first token on the same prompts."
        ),
        tags=("inference", "vllm", "triton", "tensorrt", "tokens", "performance"),
    ),
    EvaluationDocument(
        id="answer-quality-1840",
        title="Answer quality evaluation · run #1840",
        source="evaluation/quality/summary.json",
        content=(
            "The evaluation set measured 91% answer correctness, 88% retrieval recall, "
            "94% citation accuracy, and a 3% hallucination rate across 200 questions."
        ),
        tags=("evaluation", "quality", "correctness", "recall", "citation", "hallucination"),
    ),
)
