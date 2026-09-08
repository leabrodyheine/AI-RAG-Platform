"""Post-apply smoke check for a running deployment of the platform.

Unlike `validate_k8s_manifests.py`, this one needs a live cluster and a
`kubectl` context pointing at it. It checks that every Deployment in the
namespace has reported `Available`, then -- if `--host` is given -- that the
Ingress actually serves the SPA at `/` and reaches the gateway health endpoint
at `/api/health`.

    kubectl apply -k infra/kubernetes/overlays/local
    python scripts/smoke_k8s_deployment.py --host rag-platform.local

It is not part of the automated suite (there is no cluster in CI); run it by
hand or from a deploy pipeline. Prints PASS/FAIL and exits 0/1.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

import httpx

NAMESPACE = "ai-rag-platform"


def get_deployments(namespace: str) -> list[dict]:
    out = subprocess.run(
        ["kubectl", "-n", namespace, "get", "deployments", "-o", "json"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return json.loads(out).get("items", [])


def evaluate_deployments(items: list[dict]) -> list[str]:
    """Return a list of problems given `kubectl get deployments -o json` items."""
    problems: list[str] = []
    if not items:
        return ["no Deployments found in the namespace"]
    for item in items:
        name = item.get("metadata", {}).get("name", "?")
        status = item.get("status", {})
        spec = item.get("spec", {})
        desired = spec.get("replicas", 1)
        available = status.get("availableReplicas", 0)
        conditions = {c.get("type"): c for c in status.get("conditions", [])}
        available_cond = conditions.get("Available", {})
        if available_cond.get("status") != "True":
            reason = available_cond.get("reason", "no Available condition")
            problems.append(f"Deployment/{name}: not Available ({reason})")
        if available < desired:
            problems.append(
                f"Deployment/{name}: {available}/{desired} replicas available"
            )
        if conditions.get("Progressing", {}).get("reason") == "ProgressDeadlineExceeded":
            problems.append(f"Deployment/{name}: rollout deadline exceeded")
    return problems


def check_ingress(host: str, scheme: str, timeout: float) -> list[str]:
    """Hit the SPA root and the gateway health path through the Ingress."""
    problems: list[str] = []
    base = f"{scheme}://{host}"
    checks = [("/", "SPA root"), ("/api/health", "gateway health")]
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for path, label in checks:
            try:
                response = client.get(base + path)
            except httpx.HTTPError as error:
                problems.append(f"{label} {base + path}: {type(error).__name__}: {error}")
                continue
            if response.status_code != 200:
                problems.append(f"{label} {base + path}: HTTP {response.status_code}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", default=NAMESPACE)
    parser.add_argument(
        "--host",
        help="Ingress host to probe (e.g. rag-platform.local); skips HTTP checks if omitted",
    )
    parser.add_argument("--scheme", default="http", choices=("http", "https"))
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)

    problems: list[str] = []

    try:
        deployments = get_deployments(args.namespace)
    except subprocess.CalledProcessError as error:
        print(f"FAIL: kubectl get deployments errored\n{error.stderr}")
        return 1
    except FileNotFoundError:
        print("FAIL: kubectl not found on PATH")
        return 1

    deploy_problems = evaluate_deployments(deployments)
    names = sorted(d.get("metadata", {}).get("name", "?") for d in deployments)
    print(f"deployments in {args.namespace}: {', '.join(names) or '(none)'}")
    problems.extend(deploy_problems)

    if args.host:
        print(f"probing Ingress at {args.scheme}://{args.host}")
        problems.extend(check_ingress(args.host, args.scheme, args.timeout))
    else:
        print("no --host given: skipping Ingress HTTP checks")

    if problems:
        for problem in problems:
            print(f"  FAIL: {problem}")
        print("\nRESULT: FAIL")
        return 1
    print("\nRESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
