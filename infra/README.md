# Infrastructure

- `compose/` runs the CPU-compatible application and data services locally.
- `kubernetes/base/` will contain environment-independent resources.
- `kubernetes/overlays/` will contain local and GPU-specific patches.
- `observability/` owns Prometheus, Grafana, and OpenTelemetry configuration.

Keep application code in `apps/` or `services/`; infrastructure should only
describe how those deployable components run.
