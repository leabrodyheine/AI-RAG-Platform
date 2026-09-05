#!/usr/bin/env python3
"""Opt-in smoke test: one real generation through the Triton backend adapter.

    python scripts/smoke_triton.py --base-url http://localhost:8000 --model ensemble

Requires a reachable Triton TensorRT-LLM server. Not part of the automated suite.
"""

import asyncio
import sys

from _smoke import build_parser, run_smoke, stop_sequences
from inference_service.backends.triton import TritonBackend


def main() -> int:
    args = build_parser(__doc__ or "").parse_args()
    backend = TritonBackend(
        base_url=args.base_url,
        model=args.model,
        timeout_seconds=args.timeout,
        stop_sequences=stop_sequences(args.stop),
    )
    return asyncio.run(run_smoke(backend, args))


if __name__ == "__main__":
    sys.exit(main())
