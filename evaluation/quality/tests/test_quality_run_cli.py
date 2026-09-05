import json
from pathlib import Path

from evaluation.quality.run import main

DATASET_PATH = Path(__file__).resolve().parents[2] / "datasets" / "quality-core-v1.json"


def _args(tmp_path: Path, **extra: str) -> list[str]:
    args = [
        "--dataset",
        str(DATASET_PATH),
        "--json-out",
        str(tmp_path / "q.json"),
        "--markdown-out",
        str(tmp_path / "q.md"),
    ]
    for key, value in extra.items():
        args.extend([f"--{key.replace('_', '-')}", value])
    return args


def test_cli_writes_both_reports_and_exits_zero(tmp_path: Path, capsys) -> None:
    code = main(_args(tmp_path))
    assert code == 0

    payload = json.loads((tmp_path / "q.json").read_text())
    assert payload["schema"] == "quality-report/v1"
    assert payload["metrics"]["case_count"] == 15
    markdown = (tmp_path / "q.md").read_text()
    assert markdown.startswith("# Quality evaluation report")
    assert "wrote" in capsys.readouterr().out


def test_cli_quiet_prints_only_paths(tmp_path: Path, capsys) -> None:
    code = main([*_args(tmp_path), "--quiet"])
    assert code == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out == [str(tmp_path / "q.json"), str(tmp_path / "q.md")]


def test_cli_creates_missing_output_directories(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b"
    code = main(
        [
            "--dataset",
            str(DATASET_PATH),
            "--json-out",
            str(nested / "q.json"),
            "--markdown-out",
            str(nested / "q.md"),
            "--quiet",
        ]
    )
    assert code == 0
    assert (nested / "q.json").exists()


def test_cli_rejects_a_missing_dataset(tmp_path: Path, capsys) -> None:
    code = main(
        [
            "--dataset",
            str(tmp_path / "nope.json"),
            "--json-out",
            str(tmp_path / "q.json"),
            "--markdown-out",
            str(tmp_path / "q.md"),
        ]
    )
    assert code == 2
    assert "error:" in capsys.readouterr().err


def test_cli_rejects_an_unknown_judge(tmp_path: Path, capsys) -> None:
    code = main([*_args(tmp_path), "--judge", "gpt-9"])
    assert code == 2
    assert "unknown judge" in capsys.readouterr().err


def test_cli_rejects_a_non_positive_top_k(tmp_path: Path, capsys) -> None:
    code = main([*_args(tmp_path), "--top-k", "0"])
    assert code == 2
    assert "top-k" in capsys.readouterr().err
