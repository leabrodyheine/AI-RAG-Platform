# Kubernetes

Use Kustomize to share manifests without duplicating them:

- `base/` contains Deployments, Services, ConfigMaps, and common policies.
- `overlays/local/` adapts the base for kind or Minikube.
- `overlays/gpu/` adds GPU resources, selectors, taints, and tolerations.

Add manifests alongside the first working containerized workflow so probes and
resource settings can reflect measured application behavior.
