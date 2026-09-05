# OpenAPI contracts

Versioned API specifications:

- `chat-v1.openapi.json` defines the public API gateway `POST /chat` contract.
- `retrieval-v1.openapi.json` defines the internal retrieval `POST /search` contract.

The chat contract uses camelCase JSON fields to match browser conventions. A
question must contain 1–4,000 characters after trimming. Successful and error
responses always include an `X-Request-ID` correlation header.
