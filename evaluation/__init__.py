"""Offline evaluation code for the AI Production Evaluation Platform.

Kept out of the request-serving services so its dependencies never enlarge
production images. Everything here runs in-process against the deterministic
retrieval corpus and the deterministic inference backend, so a full quality
report is reproducible from a clean checkout with no GPU, model download, or
running infrastructure.
"""
