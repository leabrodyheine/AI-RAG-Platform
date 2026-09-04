# Evaluation

Offline evaluation code and reproducible experiment inputs live here. Keep this
separate from request-serving services so evaluation dependencies do not enlarge
production images.

- `quality/`: correctness, retrieval, citation, and hallucination evaluation.
- `performance/`: latency, throughput, and resource analysis.
- `datasets/`: small tracked fixtures or local ignored datasets.
- `reports/`: generated local reports; curated reports can move into `docs/`.
