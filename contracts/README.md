# Service contracts

This directory is the source of truth for schemas exchanged across service
boundaries. Prefer OpenAPI or JSON Schema over importing another service's
runtime code.

- `openapi/` contains HTTP API descriptions.
- `json-schema/` contains event or artifact schemas that are not HTTP-specific.
