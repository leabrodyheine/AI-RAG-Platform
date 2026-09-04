# ADR-0001: Use a service-oriented monorepo

**Status:** Accepted

## Context

The platform contains a React client, four Python services, two optional model
runtimes, evaluation tooling, and shared deployment configuration. These parts
must remain independently deployable without making local development difficult.

## Decision

Keep all components in one repository and organize application code by
deployable boundary. Each service owns its package metadata, tests, and
container image. Services exchange versioned contracts and do not import one
another's runtime code.

## Consequences

- A single change can update a contract and all affected consumers.
- Each service can build and deploy independently.
- Some configuration is repeated across Python services.
- Cross-service behavior requires explicit integration tests.
