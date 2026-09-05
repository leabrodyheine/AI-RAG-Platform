# Agent service

The agent turns one question into a cited answer. It owns the RAG workflow:
deciding whether to retrieve, judging evidence quality, one bounded query
rewrite, and prompting the inference service. It holds no storage and no model.

- `POST /answer` accepts a `question` (1–4,000 characters after trimming) and
  returns `content`, `citations`, a `trace`, and `totalDurationMs`. Successful
  and error responses carry an `X-Request-ID` correlation header.

## Workflow

A fixed decision loop, not an open-ended agent. States:
`plan → retrieve → assess → (rewrite → retrieve → assess) → generate`.

1. **Plan** — `decide_retrieval` is deterministic. Greetings, questions about
   the assistant, and questions with no searchable terms get a direct answer
   and stop. Everything else goes to retrieval. There is no model router yet;
   this heuristic is the fallback one would defer to.
2. **Retrieve** — call the retrieval service with the question.
3. **Assess** — keep citations at or above `AGENT_WORKFLOW_MIN_RELEVANCE`;
   evidence is *strong* when at least `AGENT_WORKFLOW_MIN_RESULTS` survive.
4. **Rewrite** — only if evidence is weak and the step budget allows. One
   deterministic keyword rewrite (interrogatives and stop words removed). If it
   is not distinct from the original, it is skipped. Retrieve again and keep
   whichever result set is stronger.
5. **Generate** — build a prompt that lists each usable citation on its own
   `[n]` line and instructs the model to answer only from that evidence. When
   no usable evidence survives, the prompt says so and the answer states that
   there is insufficient evidence rather than citing anything.

`AGENT_WORKFLOW_MAX_STEPS` caps retrieval and generation calls (the loop needs
at most three). If the budget is exhausted the run stops with a plain
"could not finish within the step limit" answer. Every path is bounded.

## Trace

The `trace` array records each step's decision, measurement, and duration —
`Plan`, `Retrieve`, `Assess evidence`, optionally `Rewrite query` /
`Retrieve after rewrite` / `Assess evidence after rewrite`, then `Generate` or
`Stop`. Labels are unique per response. No chain-of-thought or hidden prompt
text is exposed; only what was decided and measured.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `RETRIEVAL_SERVICE_URL` / `RETRIEVAL_REQUEST_TIMEOUT_SECONDS` | `http://retrieval:8002` / `5` | Retrieval service address and per-call budget. |
| `INFERENCE_SERVICE_URL` / `INFERENCE_REQUEST_TIMEOUT_SECONDS` | `http://inference:8003` / `15` | Inference service address and per-call budget. |
| `AGENT_WORKFLOW_MIN_RELEVANCE` | `0.3` | Similarity threshold (0–1) for a citation to count as usable. |
| `AGENT_WORKFLOW_MIN_RESULTS` | `1` | Usable citations needed before evidence is *strong* (no rewrite). |
| `AGENT_WORKFLOW_MAX_STEPS` | `4` | Hard ceiling on retrieval + generation calls per request. |

Invalid values fail at startup.

## Failure handling

Retrieval or inference timeouts return `504`; other retrieval or inference
failures return `503`. Details are stable and never include upstream error
text. The API gateway maps these to its existing `agent_timeout` /
`agent_unavailable` codes, so the public chat contract is unchanged.

## Tradeoffs

- **Deterministic routing and rewriting.** No extra model call, fully testable,
  reproducible. It cannot understand intent the way a model router would, so the
  direct-answer set is deliberately narrow and a single keyword rewrite is the
  only recovery from weak retrieval.
- **One rewrite, hard step cap.** Bounds latency and inference cost at the price
  of not chasing difficult questions further.
- **Threshold-based evidence quality.** Simple and visible in the trace, but a
  fixed cutoff mislabels borderline results; tune it per embedding model with
  the evaluation harness.
- **Direct answers are a fixed response.** Honest and cheap; a capable backend
  could instead answer these through inference with a no-evidence prompt.

## Current boundary

The workflow is bounded, deterministic, and fully visible through the trace.
Routing and rewriting are heuristic; replacing either with a model decision,
and tuning the thresholds against a real dataset, is the evaluation milestone's
work.
