import type { AssistantAnswer } from "../types/platform";

const retrievalCitation = {
  id: "retrieval-benchmark",
  title: "Retrieval benchmark · run #1842",
  source: "evaluation/performance/retrieval.json",
  excerpt: "Cache misses increased vector-search p95 from 112 ms to 391 ms at 32 concurrent users.",
  relevance: 0.96,
};

const traceCitation = {
  id: "trace-sample",
  title: "Trace sample · 7f3a91",
  source: "OpenTelemetry · production-like",
  excerpt: "Retrieval accounts for 46% of end-to-end request time in the uncached path.",
  relevance: 0.91,
};

export const suggestedQuestions = [
  "What is driving p95 latency?",
  "Compare cached and uncached retrieval",
  "Where does the agent spend the most time?",
];

export const initialAnswer: AssistantAnswer = {
  content:
    "Retrieval is the primary bottleneck in the latest high-concurrency run. Cache misses push vector-search p95 to 391 ms, accounting for nearly half of the end-to-end request time. The clearest next step is to increase cache coverage before changing the inference backend.",
  citations: [retrievalCitation, traceCitation],
  trace: [
    { label: "Intent", detail: "Performance investigation", durationMs: 42 },
    { label: "Retrieve", detail: "8 chunks · 2 sources", durationMs: 391 },
    { label: "Synthesize", detail: "vLLM · 214 tokens", durationMs: 416 },
  ],
  totalDurationMs: 849,
};

export function createDemoAnswer(question: string): AssistantAnswer {
  const normalizedQuestion = question.toLowerCase();

  if (normalizedQuestion.includes("cache")) {
    return {
      content:
        "Cached retrieval reduces p95 from 391 ms to 118 ms in the current benchmark, a 69.8% improvement. End-to-end p95 falls by 24%, while answer quality stays within the evaluation margin. Cache coverage is currently 63%, so raising it is the highest-leverage optimization.",
      citations: [retrievalCitation],
      trace: [
        { label: "Intent", detail: "Configuration comparison", durationMs: 38 },
        { label: "Retrieve", detail: "6 chunks · 1 source", durationMs: 118 },
        { label: "Synthesize", detail: "vLLM · 173 tokens", durationMs: 362 },
      ],
      totalDurationMs: 518,
    };
  }

  return initialAnswer;
}
