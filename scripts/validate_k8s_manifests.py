"""Offline validation for the Kubernetes kustomize builds.

Runs `kubectl kustomize` for each overlay and checks the rendered objects for
the invariants this platform relies on -- namespace, probes, resource requests,
that every Deployment's replica count has an owner, that Services and the
Ingress point at objects that exist, and that each HPA targets a real
Deployment. It needs no cluster: `kubectl kustomize` renders locally and every
check runs on the parsed YAML.

If `kubeconform` is on PATH it is also run for JSON-schema validation; when it
is absent that step is skipped with a note rather than failing.

    python scripts/validate_k8s_manifests.py

Exits 0 when every target passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = "ai-rag-platform"
TARGETS = (
    "infra/kubernetes/base",
    "infra/kubernetes/overlays/local",
    "infra/kubernetes/overlays/gpu",
)
CLUSTER_SCOPED = {"Namespace"}


def render(target: str) -> list[dict]:
    """Return the objects `kubectl kustomize <target>` produces."""
    out = subprocess.run(
        ["kubectl", "kustomize", str(REPO_ROOT / target)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [doc for doc in yaml.safe_load_all(out) if doc]


def _labels_match(selector: dict, labels: dict) -> bool:
    return all(labels.get(key) == value for key, value in selector.items())


def _pod_labels(deployment: dict) -> dict:
    return (
        deployment.get("spec", {})
        .get("template", {})
        .get("metadata", {})
        .get("labels", {})
    )


def _container_problems(kind: str, name: str, container: dict) -> list[str]:
    where = f"{kind}/{name} container {container.get('name', '?')}"
    problems = []
    if not container.get("image"):
        problems.append(f"{where}: no image")
    requests = container.get("resources", {}).get("requests", {})
    for resource in ("cpu", "memory"):
        if resource not in requests:
            problems.append(f"{where}: no resources.requests.{resource}")
    for probe in ("livenessProbe", "readinessProbe"):
        if probe not in container:
            problems.append(f"{where}: no {probe}")
    return problems


def validate_docs(docs: Iterable[dict]) -> list[str]:
    """Check one rendered target. Return a list of problems ([] means it passed)."""
    docs = list(docs)
    problems: list[str] = []

    deployments: dict[str, dict] = {}
    services: dict[str, dict] = {}
    hpa_targets: set[str] = set()

    for doc in docs:
        api_version = doc.get("apiVersion")
        kind = doc.get("kind")
        name = doc.get("metadata", {}).get("name")
        if not (api_version and kind and name):
            problems.append(f"object missing apiVersion/kind/metadata.name: {doc!r:.80}")
            continue
        namespace = doc.get("metadata", {}).get("namespace")
        if kind not in CLUSTER_SCOPED and namespace != NAMESPACE:
            problems.append(f"{kind}/{name}: namespace is {namespace!r}, expected {NAMESPACE!r}")
        if kind == "Deployment":
            deployments[name] = doc
        elif kind == "Service":
            services[name] = doc
        elif kind == "HorizontalPodAutoscaler":
            problems.extend(_hpa_problems(doc))

    for name, doc in deployments.items():
        spec = doc.get("spec", {})
        pod_spec = spec.get("template", {}).get("spec", {})
        containers = pod_spec.get("containers", [])
        if not containers:
            problems.append(f"Deployment/{name}: no containers")
        for container in containers:
            problems.extend(_container_problems("Deployment", name, container))

    # A Deployment's replica count needs exactly one owner: either a static
    # spec.replicas, or an HPA -- never both, never neither.
    for doc in docs:
        if doc.get("kind") != "HorizontalPodAutoscaler":
            continue
        ref = doc.get("spec", {}).get("scaleTargetRef", {})
        if ref.get("kind") == "Deployment" and ref.get("name"):
            hpa_targets.add(ref["name"])

    for name, doc in deployments.items():
        has_replicas = "replicas" in doc.get("spec", {})
        managed = name in hpa_targets
        if has_replicas and managed:
            problems.append(
                f"Deployment/{name}: sets spec.replicas and is an HPA target -- "
                "kubectl apply will fight the HPA"
            )
        if not has_replicas and not managed:
            problems.append(
                f"Deployment/{name}: no spec.replicas and no HPA -- replica count has no owner"
            )

    for name in hpa_targets:
        if name not in deployments:
            problems.append(f"HPA target Deployment/{name} does not exist in this build")

    for name, doc in services.items():
        selector = doc.get("spec", {}).get("selector") or {}
        if not selector:
            problems.append(f"Service/{name}: empty selector")
            continue
        backed = any(
            _labels_match(selector, _pod_labels(dep)) for dep in deployments.values()
        )
        if not backed:
            problems.append(
                f"Service/{name}: selector {selector} matches no Deployment pod template"
            )

    problems.extend(_ingress_problems(docs, services))
    return problems


def _hpa_problems(doc: dict) -> list[str]:
    name = doc["metadata"]["name"]
    spec = doc.get("spec", {})
    problems = []
    ref = spec.get("scaleTargetRef", {})
    if ref.get("kind") != "Deployment" or not ref.get("name"):
        problems.append(f"HPA/{name}: scaleTargetRef is not a named Deployment")
    lo, hi = spec.get("minReplicas"), spec.get("maxReplicas")
    if not isinstance(lo, int) or lo < 1:
        problems.append(f"HPA/{name}: minReplicas must be >= 1, got {lo!r}")
    if not isinstance(hi, int) or (isinstance(lo, int) and hi < lo):
        problems.append(f"HPA/{name}: maxReplicas {hi!r} must be >= minReplicas {lo!r}")
    if not spec.get("metrics"):
        problems.append(f"HPA/{name}: no metrics")
    return problems


def _ingress_problems(docs: list[dict], services: dict[str, dict]) -> list[str]:
    problems = []
    for doc in docs:
        if doc.get("kind") != "Ingress":
            continue
        name = doc["metadata"]["name"]
        for rule in doc.get("spec", {}).get("rules", []):
            for path in rule.get("http", {}).get("paths", []):
                backend = path.get("backend", {}).get("service", {})
                svc_name = backend.get("name")
                svc_port = backend.get("port", {}).get("number")
                svc = services.get(svc_name)
                if svc is None:
                    problems.append(f"Ingress/{name}: backend Service/{svc_name} does not exist")
                    continue
                ports = {p.get("port") for p in svc.get("spec", {}).get("ports", [])}
                if svc_port not in ports:
                    have = sorted(p for p in ports if p is not None)
                    problems.append(
                        f"Ingress/{name}: Service/{svc_name} has no port {svc_port} (has {have})"
                    )
    return problems


def run_kubeconform(target: str) -> tuple[bool, str]:
    """Schema-validate a target with kubeconform. Returns (ok, message)."""
    if shutil.which("kubeconform") is None:
        return True, "kubeconform not installed -- schema check skipped"
    rendered = subprocess.run(
        ["kubectl", "kustomize", str(REPO_ROOT / target)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    result = subprocess.run(
        ["kubeconform", "-strict", "-summary", "-ignore-missing-schemas"],
        input=rendered,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "targets",
        nargs="*",
        default=list(TARGETS),
        help="kustomize directories to check (default: base + every overlay)",
    )
    args = parser.parse_args(argv)

    failed = False
    for target in args.targets:
        print(f"== {target} ==")
        try:
            docs = render(target)
        except subprocess.CalledProcessError as error:
            print(f"  FAIL: kubectl kustomize errored\n{error.stderr}")
            failed = True
            continue

        problems = validate_docs(docs)
        kinds = sorted({doc["kind"] for doc in docs})
        print(f"  {len(docs)} objects: {', '.join(kinds)}")

        ok, message = run_kubeconform(target)
        print(f"  kubeconform: {message}")
        failed = failed or not ok

        if problems:
            failed = True
            for problem in problems:
                print(f"  FAIL: {problem}")
        else:
            print("  invariants: OK")

    print("\nRESULT:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
