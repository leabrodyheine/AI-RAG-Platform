"""Quality evaluation: retrieval, citation, answer correctness, and hallucination.

The public entry point is :mod:`evaluation.quality.run` (``python -m
evaluation.quality.run``), which loads a versioned dataset, replays it through
the real agent workflow in-process, scores it, and writes a machine-readable
report and a human-readable one.
"""
