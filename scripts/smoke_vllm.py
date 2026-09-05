#!/usr/bin/env python3
"""Opt-in smoke test: one real generation through the vLLM backend adapter.

    python scripts/smoke_vllm.py --base-url http://localhost:8000 \
        --model meta-llama/Llama-3.1-8B-Instruct

Requires a reachable vLLM server. Not part of the automated suite.
"""

import asyncio
import sys

from _smoke import build_parser, run_smoke, stop_sequences
from inference_service.backends.vllm import VLLMBackend


def main() -> int:
    args = build_parser(__doc__ or "").parse_args()
    backend = VLLMBackend(
        base_url=args.base_url,
        model=args.model,
        timeout_seconds=args.timeout,
        stop_sequences=stop_sequences(args.stop),
    )
    return asyncio.run(run_smoke(backend, args))


if __name__ == "__main__":
    sys.exit(main())
