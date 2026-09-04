# AI Production Evaluation Platform

A **cloud-native AI system** that benchmarks and monitors its own performance, then uses an agentic RAG interface to let engineers investigate performance results, identify bottlenecks, and compare architectural configurations using natural-language questions.

## Architecture

![Proposed architecture showing the web client, Kubernetes services, retrieval stores, GPU inference backends, and observability.](docs/diagrams/architecture.png)

| Component | Choice | Why |
| --- | --- | --- |
| Frontend | React + TypeScript | Matches the JD's JavaScript requirement and keeps the UI realistic but lightweight. |
| API Gateway | FastAPI | Python-first, async, simple API design, easy service boundaries. |
| Agent Service | Python | Runs tool-calling, query rewriting, retrieval decisions, and answer synthesis. |
| Retrieval | pgvector | Keeps vector search close to Postgres and avoids adding another database for a portfolio project. |
| Cache | Redis | Demonstrates caching, queueing, and bottleneck reduction. |
| Inference | vLLM + Triton/TensorRT-LLM | Directly maps to the JD and enables performance comparison between inference stacks. |
| Containers | Docker | Reproducible services and required foundation for Kubernetes. |
| Orchestration | Kubernetes | Demonstrates deployments, services, ingress, autoscaling, probes, resource limits, and GPU scheduling. |
| Observability | Prometheus + Grafana + OpenTelemetry | Measures system health and traces latency across services. |

## Request Flow

![Proposed agentic request flow with optional retrieval, a query-rewrite loop, inference, and a cited response.](docs/diagrams/request-flow.png)

1. User submits a question.
2. Agent decides whether retrieval is needed.
3. Retrieval service searches embedded document chunks.
4. Agent may rewrite the query or retrieve again if evidence is weak.
5. Inference service sends the final prompt to **vLLM or Triton/TensorRT-LLM**.
6. Response is returned with citations.
7. Metrics and traces are recorded for evaluation.

## Deployment

Run the full stack locally with Docker and Kubernetes (`kind` or Minikube). GPU workloads are isolated behind the inference service so they can run locally when available or in a free NVIDIA GPU environment.

## Repository Layout

| Path | Responsibility |
| --- | --- |
| `apps/web/` | React and TypeScript web client. |
| `services/` | Independently packaged API gateway, agent, retrieval, and inference services. |
| `runtimes/` | vLLM and Triton/TensorRT-LLM runtime configuration. |
| `evaluation/` | Offline quality and performance evaluation. |
| `load-tests/` | Reproducible load scenarios and local results. |
| `contracts/` | Versioned schemas exchanged across service boundaries. |
| `infra/` | Docker Compose, Kubernetes, and observability configuration. |
| `tests/` | Cross-service integration and end-to-end tests. |
| `docs/` | Architecture decisions, diagrams, operations, and published reports. |

Each service owns its dependencies, unit tests, and Dockerfile. Services communicate through explicit network contracts and do not import each other's implementation code.

Kubernetes configuration includes:

- Deployments and Services
- Ingress
- ConfigMaps and Secrets
- readiness/liveness probes
- CPU/GPU resource limits
- Horizontal Pod Autoscaling
- GPU node selectors / taints / tolerations

## Evaluation

The system evaluates both **AI quality** and **systems performance**.

**Quality**

- answer correctness
- retrieval recall
- citation accuracy
- hallucination rate

**Performance**

- p50 / p95 / p99 latency
- time to first token
- tokens/sec
- requests/sec
- GPU utilization / memory
- retrieval latency
- error rate

Compare:

- basic RAG vs agentic RAG
- vLLM vs Triton/TensorRT-LLM
- low vs high concurrency
- cached vs uncached retrieval

## Intended Bottleneck Exercise

Load-test the system, identify the slowest stage using metrics/tracing, then optimize it.

Example:

`high p95 latency -> retrieval CPU bottleneck -> async calls + Redis cache -> lower latency / higher throughput`

The final report should explain the bottleneck, evidence, fix, and measured improvement.

## Key Tradeoffs

| Decision | Tradeoff |
| --- | --- |
| Microservices vs monolith | More realistic scaling/debugging experience, but more operational complexity. |
| pgvector vs dedicated vector DB | Simpler stack and fewer services, but less specialized vector-search functionality. |
| vLLM vs Triton/TensorRT-LLM | vLLM is easier to operate; Triton/TensorRT-LLM offers deeper NVIDIA optimization and serving control. |
| Agentic RAG vs basic RAG | Better handling of complex questions, but higher latency and more inference calls. |
| Local Kubernetes vs managed cloud | Free and sufficient for learning orchestration, but not equivalent to operating a production cloud cluster. |
| Redis caching | Improves latency and load behavior, but adds cache invalidation and consistency concerns. |
| REST vs gRPC | REST is simpler and easier to debug; gRPC can be more efficient for internal service communication. |

## Deliverables

- working full-stack application
- Dockerfiles for every service
- Kubernetes manifests
- vLLM inference backend
- Triton/TensorRT-LLM inference backend
- RAG + agent workflow
- load-testing and evaluation scripts
- Grafana dashboard
- architecture diagrams
- short performance report with recommendations
- public tutorial / README
