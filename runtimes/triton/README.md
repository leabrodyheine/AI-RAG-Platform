# Triton / TensorRT-LLM runtime

Serves the reference model through Triton's TensorRT-LLM backend. The inference
service's `triton` backend calls `POST /v2/models/ensemble/generate`.

## Prerequisites

See [`../README.md`](../README.md) for the shared GPU, driver, memory, and
model-license requirements. TensorRT-LLM additionally needs an NVIDIA GPU of
compute capability 8.0+ (Ampere or newer), because the engine is compiled for
the target architecture, and roughly 40 GB of disk for the checkpoint plus the
built engine.

## Pinned versions

| Component | Pin |
| --- | --- |
| Server image | `nvcr.io/nvidia/tritonserver:24.08-trtllm-python-py3` |
| `tensorrtllm_backend` | tag `v0.12.0` |
| Model | `meta-llama/Llama-3.1-8B-Instruct` |

## What is committed here

`model_repository/` holds only trimmed templates:

- `ensemble/config.pbtxt` — the `text_input -> text_output` graph the adapter calls.
- `tensorrt_llm/config.pbtxt` — the decoder config with the reproducibility knobs
  (`gpt_model_type`, `decoding_mode`, `batch_scheduler_policy`,
  `exclude_input_in_output`).

`preprocessing/` and `postprocessing/` are **not** committed: they are Python
models copied unmodified from `tensorrtllm_backend` with only the tokenizer path
filled in. Built engines and weights stay out of Git.

## Prepare the engine and repository

Placeholders below: `${ENGINE_DIR}` is the built-engine output path,
`${MAX_BATCH_SIZE}` (start with `8`), `${MAX_INPUT_LEN}` (`4096`),
`${MAX_OUTPUT_LEN}` (`2048`).

```bash
# 1. Pin the backend templates.
git clone -b v0.12.0 https://github.com/triton-inference-server/tensorrtllm_backend.git
cd tensorrtllm_backend

# 2. Convert the HF checkpoint and build the engine for this GPU.
python tensorrt_llm/examples/llama/convert_checkpoint.py \
  --model_dir meta-llama/Llama-3.1-8B-Instruct \
  --output_dir ./ckpt --dtype bfloat16
trtllm-build --checkpoint_dir ./ckpt --output_dir ${ENGINE_DIR} \
  --gemm_plugin bfloat16 \
  --max_batch_size ${MAX_BATCH_SIZE} \
  --max_input_len ${MAX_INPUT_LEN} \
  --max_seq_len $((${MAX_INPUT_LEN} + ${MAX_OUTPUT_LEN}))

# 3. Assemble the repository: start from the upstream templates, then overlay
#    the two committed templates from this directory.
cp -r all_models/inflight_batcher_llm/{preprocessing,postprocessing} \
  <repo>/runtimes/triton/model_repository/
python tools/fill_template.py -i \
  <repo>/runtimes/triton/model_repository/preprocessing/config.pbtxt \
  tokenizer_dir:meta-llama/Llama-3.1-8B-Instruct,triton_max_batch_size:${MAX_BATCH_SIZE}
python tools/fill_template.py -i \
  <repo>/runtimes/triton/model_repository/postprocessing/config.pbtxt \
  tokenizer_dir:meta-llama/Llama-3.1-8B-Instruct,triton_max_batch_size:${MAX_BATCH_SIZE}
# Then replace ${...} in ensemble/config.pbtxt and tensorrt_llm/config.pbtxt.
```

## Start the server

```bash
docker run --rm --gpus all \
  -p 8000:8000 -p 8001:8001 -p 8002:8002 \
  -v "$PWD/runtimes/triton/model_repository:/models" \
  -v "${ENGINE_DIR}:${ENGINE_DIR}" \
  nvcr.io/nvidia/tritonserver:24.08-trtllm-python-py3 \
  tritonserver --model-repository=/models
```

## Verify

```bash
curl -sf http://localhost:8000/v2/health/ready        # server up
curl -sf http://localhost:8000/v2/models/ensemble/ready  # model loaded
```

The inference service's `/ready` mirrors the second check.

## Point the inference service at it

```bash
INFERENCE_BACKEND=triton
TRITON_BASE_URL=http://localhost:8000     # http://host.docker.internal:8000 from Compose
INFERENCE_MODEL=ensemble
INFERENCE_BACKEND_TIMEOUT_SECONDS=60
INFERENCE_STOP_SEQUENCES=<|eot_id|>
```

## Smoke test

```bash
python scripts/smoke_triton.py --base-url http://localhost:8000 --model ensemble
```
