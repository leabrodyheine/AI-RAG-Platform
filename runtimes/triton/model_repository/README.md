# Triton model repository

Only trimmed, reusable templates are committed:

- `ensemble/config.pbtxt` — the `text_input -> text_output` graph the inference
  service calls at `POST /v2/models/ensemble/generate`.
- `tensorrt_llm/config.pbtxt` — decoder config carrying the reproducibility
  parameters.

`preprocessing/` and `postprocessing/` are added during setup from the pinned
`tensorrtllm_backend` repo. Placeholders written as `${NAME}` and built
TensorRT engines and downloaded weights are filled in or produced by the steps
in [`../README.md`](../README.md) and are never committed.
