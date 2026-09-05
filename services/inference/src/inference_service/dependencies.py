from typing import cast

from fastapi import Request

from inference_service.backends import InferenceBackend


def get_backend(request: Request) -> InferenceBackend:
    return cast(InferenceBackend, request.app.state.backend)
