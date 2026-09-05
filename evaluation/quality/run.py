"""Command line entry point: ``python -m evaluation.quality.run``.

Loads the dataset, replays it through the agent workflow in-process, writes a
machine-readable JSON report and a human-readable Markdown one, and prints a
short summary. Everything is deterministic and offline, so the same checkout
produces the same report.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evaluation.quality.harness import DEFAULT_TOP_K, run_evaluation
from evaluation.quality.judge import create_judge
from evaluation.quality.report import build_report, render_markdown
from evaluation.quality.schema import DatasetError, load_dataset

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = _REPO_ROOT / "evaluation" / "datasets" / "quality-core-v1.json"
DEFAULT_JSON_OUT = _REPO_ROOT / "evaluation" / "reports" / "quality-latest.json"
DEFAULT_MARKDOWN_OUT = _REPO_ROOT / "evaluation" / "reports" / "quality-latest.md"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation.quality.run",
        description="Run the offline quality evaluation and write its reports.",
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--markdown-out", type=Path, default=DEFAULT_MARKDOWN_OUT)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--judge", default="keyword", help="answer-correctness judge")
    parser.add_argument(
        "--quiet", action="store_true", help="only print the output file paths"
    )
    return parser


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.top_k < 1:
        print("error: --top-k must be at least 1", file=sys.stderr)
        return 2
    try:
        dataset = load_dataset(args.dataset)
    except DatasetError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    try:
        judge = create_judge(args.judge)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    run = run_evaluation(dataset, judge=judge, top_k=args.top_k)
    report = build_report(run)

    _write(args.json_out, json.dumps(report, indent=2, sort_keys=True))
    markdown = render_markdown(report)
    _write(args.markdown_out, markdown)

    if args.quiet:
        print(args.json_out)
        print(args.markdown_out)
    else:
        print(markdown)
        print(f"\nwrote {args.json_out}")
        print(f"wrote {args.markdown_out}")
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
