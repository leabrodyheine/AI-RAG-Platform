# vLLM configuration

[`llama-3.1-8b-instruct.yaml`](llama-3.1-8b-instruct.yaml) is the pinned engine
configuration for the reference model: model identity, dtype, seed, context
length, GPU memory fraction, and tensor-parallel size. Every output-affecting
value is explicit so runs are reproducible.

`served-model-name` in that file must equal `INFERENCE_MODEL`. The tokenizer is
intentionally not overridden so vLLM uses the one shipped with the model.

Do not commit downloaded model weights.
