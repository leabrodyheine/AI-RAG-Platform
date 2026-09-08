import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "validate_k8s_manifests.py"
_spec = importlib.util.spec_from_file_location("validate_k8s_manifests", _MODULE_PATH)
assert _spec and _spec.loader
validate = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = validate
_spec.loader.exec_module(validate)


def _deployment(name, *, replicas=None, probes=True, requests=True):
    container = {"name": name, "image": f"img/{name}:latest"}
    if requests:
        container["resources"] = {"requests": {"cpu": "100m", "memory": "128Mi"}}
    if probes:
        container["livenessProbe"] = {"httpGet": {"path": "/health", "port": "http"}}
        container["readinessProbe"] = {"httpGet": {"path": "/health", "port": "http"}}
    spec = {
        "selector": {"matchLabels": {"app.kubernetes.io/name": name}},
        "template": {
            "metadata": {"labels": {"app.kubernetes.io/name": name}},
            "spec": {"containers": [container]},
        },
    }
    if replicas is not None:
        spec["replicas"] = replicas
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name, "namespace": validate.NAMESPACE},
        "spec": spec,
    }


def _service(name, port=8000):
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": name, "namespace": validate.NAMESPACE},
        "spec": {
            "selector": {"app.kubernetes.io/name": name},
            "ports": [{"name": "http", "port": port}],
        },
    }


def _hpa(name, target, lo=1, hi=4):
    return {
        "apiVersion": "autoscaling/v2",
        "kind": "HorizontalPodAutoscaler",
        "metadata": {"name": name, "namespace": validate.NAMESPACE},
        "spec": {
            "scaleTargetRef": {"apiVersion": "apps/v1", "kind": "Deployment", "name": target},
            "minReplicas": lo,
            "maxReplicas": hi,
            "metrics": [{"type": "Resource", "resource": {"name": "cpu"}}],
        },
    }


def test_clean_build_has_no_problems():
    docs = [
        _deployment("web", replicas=2),
        _service("web", port=80),
        _deployment("agent"),
        _service("agent", port=8001),
        _hpa("agent", "agent"),
    ]
    assert validate.validate_docs(docs) == []


def test_missing_namespace_is_flagged():
    dep = _deployment("web", replicas=1)
    dep["metadata"].pop("namespace")
    problems = validate.validate_docs([dep, _service("web", port=80)])
    assert any("namespace is None" in p for p in problems)


def test_namespace_object_is_not_required_to_be_namespaced():
    ns = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": validate.NAMESPACE}}
    assert validate.validate_docs([ns]) == []


def test_replica_count_needs_exactly_one_owner():
    both = validate.validate_docs(
        [_deployment("agent", replicas=1), _service("agent", 8001), _hpa("a", "agent")]
    )
    assert any("fight the HPA" in p for p in both)

    neither = validate.validate_docs([_deployment("agent"), _service("agent", 8001)])
    assert any("no owner" in p for p in neither)


def test_hpa_pointing_at_missing_deployment():
    problems = validate.validate_docs([_hpa("ghost", "ghost")])
    assert any("does not exist" in p for p in problems)


def test_hpa_bounds_are_checked():
    problems = validate.validate_docs(
        [_deployment("agent"), _service("agent", 8001), _hpa("a", "agent", lo=5, hi=2)]
    )
    assert any("maxReplicas" in p for p in problems)


def test_container_must_have_requests_and_probes():
    problems = validate.validate_docs(
        [_deployment("web", replicas=1, probes=False, requests=False), _service("web", 80)]
    )
    joined = "\n".join(problems)
    assert "resources.requests.cpu" in joined
    assert "livenessProbe" in joined


def test_service_selector_must_match_a_deployment():
    problems = validate.validate_docs([_deployment("web", replicas=1), _service("orphan", 80)])
    assert any("matches no Deployment" in p for p in problems)


def test_ingress_backends_must_resolve():
    ingress = {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "Ingress",
        "metadata": {"name": "rag-platform", "namespace": validate.NAMESPACE},
        "spec": {
            "rules": [
                {
                    "http": {
                        "paths": [
                            {"backend": {"service": {"name": "web", "port": {"number": 80}}}},
                            {"backend": {"service": {"name": "web", "port": {"number": 999}}}},
                            {"backend": {"service": {"name": "gone", "port": {"number": 80}}}},
                        ]
                    }
                }
            ]
        },
    }
    problems = validate.validate_docs(
        [_deployment("web", replicas=1), _service("web", 80), ingress]
    )
    joined = "\n".join(problems)
    assert "no port 999" in joined
    assert "Service/gone does not exist" in joined
    assert "no port 80" not in joined  # the valid backend is not flagged


@pytest.mark.skipif(shutil.which("kubectl") is None, reason="kubectl not installed")
def test_real_kustomize_targets_pass():
    for target in validate.TARGETS:
        try:
            docs = validate.render(target)
        except subprocess.CalledProcessError as error:  # pragma: no cover - surfaced in CI
            pytest.fail(f"{target}: kubectl kustomize failed: {error.stderr}")
        assert validate.validate_docs(docs) == [], target
