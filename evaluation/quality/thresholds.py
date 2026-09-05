"""CI regression gate: compare a run's metrics against committed thresholds.

``min`` entries are floors (the metric must be at least the value); ``max``
entries are ceilings (at most). The committed thresholds live in
``thresholds.json`` next to this module and are set just beneath the
deterministic baseline so a genuine regression fails CI.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_THRESHOLDS_PATH = Path(__file__).with_name("thresholds.json")

# Metrics a threshold may reference (the scalar fields of QualityMetrics).
_SCORE_METRICS = frozenset(
    {
        "retrieval_recall",
        "retrieval_mrr",
        "retrieval_precision_at_1",
        "citation_presence",
        "citation_accuracy",
        "answer_correctness",
        "answer_score",
        "hallucination_rate",
    }
)


class ThresholdError(ValueError):
    """A thresholds file is missing or malformed."""


@dataclass(frozen=True)
class Regression:
    metric: str
    value: float
    threshold: float
    direction: str  # "floor" | "ceiling"

    def as_dict(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "value": self.value,
            "threshold": self.threshold,
            "direction": self.direction,
        }


@dataclass(frozen=True)
class Thresholds:
    minimums: dict[str, float]
    maximums: dict[str, float]

    def as_dict(self) -> dict[str, dict[str, float]]:
        return {"min": dict(self.minimums), "max": dict(self.maximums)}


def _coerce_bounds(raw: object, *, label: str) -> dict[str, float]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ThresholdError(f"thresholds '{label}' must be an object")
    bounds: dict[str, float] = {}
    for key, value in raw.items():
        if key not in _SCORE_METRICS:
            raise ThresholdError(f"thresholds '{label}' has unknown metric {key!r}")
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise ThresholdError(f"threshold {label}.{key} must be a number")
        if not 0.0 <= float(value) <= 1.0:
            raise ThresholdError(f"threshold {label}.{key} must be between 0 and 1")
        bounds[key] = float(value)
    return bounds


def parse_thresholds(payload: object) -> Thresholds:
    if not isinstance(payload, dict):
        raise ThresholdError("thresholds root must be a JSON object")
    minimums = _coerce_bounds(payload.get("min"), label="min")
    maximums = _coerce_bounds(payload.get("max"), label="max")
    if not minimums and not maximums:
        raise ThresholdError("thresholds file sets no bounds")
    return Thresholds(minimums=minimums, maximums=maximums)


def load_thresholds(path: str | Path = DEFAULT_THRESHOLDS_PATH) -> Thresholds:
    threshold_path = Path(path)
    try:
        raw = threshold_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ThresholdError(f"cannot read thresholds {threshold_path}: {error}") from error
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ThresholdError(f"thresholds {threshold_path} is not valid JSON: {error}") from error
    return parse_thresholds(payload)


def check_thresholds(metrics: dict, thresholds: Thresholds) -> list[Regression]:
    """Return one Regression per breached bound; empty means the gate passes."""
    regressions: list[Regression] = []
    for metric, floor in thresholds.minimums.items():
        value = metrics.get(metric)
        if value is not None and value < floor:
            regressions.append(Regression(metric, float(value), floor, "floor"))
    for metric, ceiling in thresholds.maximums.items():
        value = metrics.get(metric)
        if value is not None and value > ceiling:
            regressions.append(Regression(metric, float(value), ceiling, "ceiling"))
    return regressions
