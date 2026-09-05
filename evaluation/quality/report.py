"""Assemble a run into a machine-readable report and a human-readable one.

``build_report`` returns a plain dict (JSON-serialisable) with a ``run`` block
that captures everything needed to reproduce the numbers -- dataset version and
hash, retrieval mode, inference backend and model, workflow thresholds, judge,
commit SHA, Python version -- plus the aggregate metrics and every per-case
outcome. ``render_markdown`` turns that dict into the report a person reads.
"""

from __future__ import annotations

import platform
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime

from evaluation.quality.harness import RunResult

REPORT_SCHEMA = "quality-report/v1"

# metric -> (label, "floor" | "ceiling")
_METRIC_LABELS: dict[str, tuple[str, str]] = {
    "retrieval_recall": ("Retrieval recall", "floor"),
    "retrieval_mrr": ("Retrieval MRR", "floor"),
    "retrieval_precision_at_1": ("Retrieval precision@1", "floor"),
    "citation_presence": ("Citation presence", "floor"),
    "citation_accuracy": ("Citation accuracy", "floor"),
    "answer_correctness": ("Answer correctness", "floor"),
    "answer_score": ("Answer score (soft)", "floor"),
    "hallucination_rate": ("Hallucination rate", "ceiling"),
}


def resolve_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def build_report(
    run: RunResult,
    *,
    commit: str | None = None,
    generated_at: datetime | None = None,
    thresholds: dict | None = None,
    regressions: list[dict] | None = None,
) -> dict:
    dataset = run.dataset
    moment = (generated_at or datetime.now(UTC)).astimezone(UTC)
    report: dict = {
        "schema": REPORT_SCHEMA,
        "run": {
            "generated_at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "commit": commit if commit is not None else resolve_commit(),
            "python_version": platform.python_version(),
            "dataset": {
                "version": dataset.version,
                "path": str(dataset.source_path) if dataset.source_path else None,
                "sha256": dataset.sha256,
                "case_count": len(dataset.cases),
                "embedding_version": dataset.embedding_version,
            },
            "retrieval": {
                "mode": run.retrieval_mode,
                "corpus_size": run.corpus_size,
                "top_k": run.top_k,
            },
            "inference": {
                "backend": run.inference_backend,
                "model": run.inference_model,
            },
            "workflow": asdict(run.workflow_config),
            "judge": run.judge_name,
        },
        "metrics": run.metrics.as_dict(),
        "cases": [_case_dict(result) for result in run.results],
        "thresholds": thresholds,
        "regressions": regressions or [],
    }
    return report


def _case_dict(result) -> dict:
    return {
        "case_id": result.case_id,
        "kind": result.kind,
        "question": result.question,
        "answer": result.answer,
        "ranked_retrieval": list(result.ranked_retrieval),
        "workflow_retrieved": list(result.workflow_retrieved),
        "cited": list(result.cited),
        "trace": list(result.trace),
        "retrieval_recall": result.retrieval_recall,
        "reciprocal_rank": result.reciprocal_rank,
        "precision_at_1": result.precision_at_1,
        "citation_present": result.citation_present,
        "citation_accuracy": result.citation_accuracy,
        "answer_passed": result.answer_passed,
        "answer_score": result.answer_score,
        "answer_rationale": result.answer_rationale,
        "hallucinated": result.hallucinated,
        "hallucination_reason": result.hallucination_reason,
    }


def _fmt(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    if value is None:
        return "-"
    return str(value)


def render_markdown(report: dict) -> str:
    run = report["run"]
    metrics = report["metrics"]
    thresholds = report.get("thresholds") or {}
    floors = thresholds.get("min", {})
    ceilings = thresholds.get("max", {})
    regressions = report.get("regressions") or []

    lines: list[str] = []
    lines.append("# Quality evaluation report")
    lines.append("")
    status = "FAIL" if regressions else "PASS"
    lines.append(f"**Status:** {status}")
    lines.append("")

    lines.append("## Run")
    lines.append("")
    lines.append(f"- Generated: `{run['generated_at']}`")
    lines.append(f"- Commit: `{run['commit']}`")
    lines.append(f"- Python: `{run['python_version']}`")
    lines.append(
        f"- Dataset: `{run['dataset']['version']}` "
        f"({run['dataset']['case_count']} cases, `sha256:{run['dataset']['sha256'][:12]}…`)"
    )
    lines.append(
        f"- Retrieval: {run['retrieval']['mode']} over {run['retrieval']['corpus_size']} "
        f"documents, top_k={run['retrieval']['top_k']}"
    )
    lines.append(
        f"- Inference: {run['inference']['backend']} / `{run['inference']['model']}`"
    )
    workflow = run["workflow"]
    lines.append(
        f"- Workflow: min_relevance={workflow['min_relevance']}, "
        f"min_results={workflow['min_results']}, max_steps={workflow['max_steps']}"
    )
    lines.append(f"- Judge: {run['judge']}")
    lines.append("")

    lines.append("## Metrics")
    lines.append("")
    has_thresholds = bool(floors or ceilings)
    if has_thresholds:
        lines.append("| Metric | Value | Threshold | Status |")
        lines.append("| --- | --- | --- | --- |")
    else:
        lines.append("| Metric | Value |")
        lines.append("| --- | --- |")
    for key, (label, direction) in _METRIC_LABELS.items():
        value = metrics.get(key)
        if value is None:
            continue
        if not has_thresholds:
            lines.append(f"| {label} | {_fmt(value)} |")
            continue
        if direction == "ceiling" and key in ceilings:
            bound = ceilings[key]
            ok = value <= bound
            bound_text = f"≤ {_fmt(bound)}"
        elif direction == "floor" and key in floors:
            bound = floors[key]
            ok = value >= bound
            bound_text = f"≥ {_fmt(bound)}"
        else:
            bound_text = "-"
            ok = True
        lines.append(
            f"| {label} | {_fmt(value)} | {bound_text} | {'ok' if ok else 'REGRESSED'} |"
        )
    lines.append("")
    lines.append(f"Cases scored: {metrics['case_count']}")
    lines.append("")

    lines.append("## By case kind")
    lines.append("")
    lines.append("| Kind | Cases | Answer correctness | Hallucination rate | Retrieval recall |")
    lines.append("| --- | --- | --- | --- | --- |")
    for kind, bucket in metrics.get("by_kind", {}).items():
        lines.append(
            f"| {kind} | {bucket['case_count']} | {_fmt(bucket['answer_correctness'])} | "
            f"{_fmt(bucket['hallucination_rate'])} | {_fmt(bucket['retrieval_recall'])} |"
        )
    lines.append("")

    if regressions:
        lines.append("## Regressions")
        lines.append("")
        for item in regressions:
            lines.append(
                f"- **{item['metric']}**: {_fmt(item['value'])} "
                f"{'>' if item['direction'] == 'ceiling' else '<'} "
                f"threshold {_fmt(item['threshold'])}"
            )
        lines.append("")

    lines.append("## Cases")
    lines.append("")
    lines.append("| Case | Kind | Correct | Recall | Cited | Hallucinated |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for case in report["cases"]:
        cited = ", ".join(case["cited"]) or "-"
        halluc = case["hallucination_reason"] if case["hallucinated"] else "no"
        lines.append(
            f"| {case['case_id']} | {case['kind']} | "
            f"{'yes' if case['answer_passed'] else 'NO'} | "
            f"{_fmt(case['retrieval_recall'])} | {cited} | {halluc} |"
        )
    lines.append("")
    return "\n".join(lines)
