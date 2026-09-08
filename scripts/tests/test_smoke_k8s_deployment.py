import importlib.util
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "smoke_k8s_deployment.py"
_spec = importlib.util.spec_from_file_location("smoke_k8s_deployment", _MODULE_PATH)
assert _spec and _spec.loader
smoke = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = smoke
_spec.loader.exec_module(smoke)


def _item(
    name,
    *,
    desired=1,
    available=1,
    avail_status="True",
    progressing_reason="NewReplicaSetAvailable",
):
    return {
        "metadata": {"name": name},
        "spec": {"replicas": desired},
        "status": {
            "availableReplicas": available,
            "conditions": [
                {"type": "Available", "status": avail_status, "reason": "MinimumReplicasAvailable"},
                {"type": "Progressing", "status": "True", "reason": progressing_reason},
            ],
        },
    }


def test_all_available_is_clean():
    items = [_item("web", desired=2, available=2), _item("agent")]
    assert smoke.evaluate_deployments(items) == []


def test_empty_namespace_is_a_problem():
    assert smoke.evaluate_deployments([]) == ["no Deployments found in the namespace"]


def test_unavailable_condition_is_flagged():
    problems = smoke.evaluate_deployments([_item("agent", available=0, avail_status="False")])
    assert any("not Available" in p for p in problems)
    assert any("0/1 replicas available" in p for p in problems)


def test_partial_rollout_is_flagged():
    problems = smoke.evaluate_deployments([_item("web", desired=3, available=1)])
    assert problems == ["Deployment/web: 1/3 replicas available"]


def test_progress_deadline_exceeded_is_flagged():
    problems = smoke.evaluate_deployments(
        [_item("agent", progressing_reason="ProgressDeadlineExceeded")]
    )
    assert any("rollout deadline exceeded" in p for p in problems)


def test_missing_replicas_field_defaults_to_one():
    item = _item("agent")
    item["spec"].pop("replicas")
    assert smoke.evaluate_deployments([item]) == []
