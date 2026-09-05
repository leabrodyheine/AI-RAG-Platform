# Project scripts

Add repeatable developer and CI tasks here when they are too involved for the
Makefile. Scripts should be non-interactive and safe to rerun.

## GPU backend smoke tests

`smoke_vllm.py` and `smoke_triton.py` drive one real generation through the same
backend adapter the inference service uses, then print `PASS`/`FAIL` and exit
`0`/`1`. They need a reachable GPU model server and are deliberately excluded
from the automated suite. `_smoke.py` is their shared runner.

```bash
python scripts/smoke_vllm.py --base-url http://localhost:8000 \
  --model meta-llama/Llama-3.1-8B-Instruct
python scripts/smoke_triton.py --base-url http://localhost:8000 --model ensemble
```

See [`runtimes/vllm/README.md`](../runtimes/vllm/README.md) and
[`runtimes/triton/README.md`](../runtimes/triton/README.md) for starting the
servers.
