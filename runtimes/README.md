# GPU runtimes

Runtime-specific serving configuration lives here. The inference service owns
backend selection; these directories configure the actual model servers.

- [`vllm/`](vllm/) — OpenAI-compatible server for the `vllm` backend.
- [`triton/`](triton/) — Triton TensorRT-LLM server for the `triton` backend.

Selecting a backend is configuration only (`INFERENCE_BACKEND` plus
`VLLM_BASE_URL` or `TRITON_BASE_URL`); no application code changes.

## Shared prerequisites

Both runtimes need:

| Requirement | Detail |
| --- | --- |
| GPU | One NVIDIA GPU, compute capability 8.0+ (Ampere or newer). vLLM reference config assumes ≥24 GB; TensorRT-LLM compiles engines for the specific architecture. |
| Host memory | ≥32 GB RAM for checkpoint conversion and engine builds. |
| Driver | NVIDIA driver ≥550 with CUDA 12.4+ support, plus the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/) so `docker run --gpus all` works. |
| Disk | ~20 GB for vLLM weights; ~40 GB for the Triton checkpoint and built engine. |
| Model license | `meta-llama/Llama-3.1-8B-Instruct` is gated. Accept the license on Hugging Face and export `HUGGING_FACE_HUB_TOKEN`. |
| Network | Outbound access to `huggingface.co` (weights) and `nvcr.io` / Docker Hub (server images) on first run. |

Automated tests never require any of the above: they run the `deterministic`
backend. These servers are only needed to compare real inference stacks.

Generated engines, converted checkpoints, and downloaded weights are never
committed.
