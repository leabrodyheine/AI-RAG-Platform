"""Shared runner for the opt-in GPU backend smoke tests.

Each smoke script drives one real generation through the *same* backend adapter
the inference service uses, so a pass means production code works against that
server. These require a reachable GPU model server and are not part of the
automated test suite.
"""

import argparse
from collections.abc import Sequence

DEFAULT_PROMPT = (
    "You answer using only the supplied evidence.\n\n"
    "Question: In one sentence, what does a smoke test verify?\n\n"
    "Evidence:\n"
    "[1] Definition — A smoke test checks that basic functionality works before "
    "deeper testing.\n\n"
    "Answer using only the evidence above."
)


def build_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--base-url", required=True, help="model server base URL")
    parser.add_argument("--model", required=True, help="served model name")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--stop",
        action="append",
        metavar="SEQUENCE",
        help="stop sequence, repeatable",
    )
    return parser


def stop_sequences(values: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(values) if values else ()


async def run_smoke(backend: object, args: argparse.Namespace) -> int:
    """Check readiness, run one generation, print PASS/FAIL, return an exit code."""
    try:
        if not await backend.ready():  # type: ignore[attr-defined]
            print(f"FAIL: {backend.name} backend at {args.base_url} is not ready")  # type: ignore[attr-defined]
            return 1
        result = await backend.generate(  # type: ignore[attr-defined]
            args.prompt,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
    except Exception as error:  # noqa: BLE001 - a smoke test reports any failure
        print(f"FAIL: {type(error).__name__}: {error}")
        return 1
    finally:
        await backend.aclose()  # type: ignore[attr-defined]

    if not result.content.strip():
        print("FAIL: the backend returned empty content")
        return 1

    print("PASS")
    print(f"  model             {backend.model}")  # type: ignore[attr-defined]
    print(f"  prompt tokens     {result.prompt_tokens}")
    print(f"  completion tokens {result.completion_tokens}")
    print(f"  content           {result.content.strip()[:200]}")
    return 0
