from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import jinja2
import yaml

REPO = Path(__file__).resolve().parents[2]
ROLE = REPO / "roles" / "openclaw_k8s"
CHART = REPO / "charts" / "openclaw" / "0.1.0"
DEFAULTS = ROLE / "defaults" / "main.yml"
EXAMPLE = REPO / "inventory" / "example" / "group_vars" / "openclaw_k3s.yml"
VALUES_TEMPLATE = ROLE / "templates" / "values-openclaw.yml.j2"
DIGEST = "sha256:f40d1e66fd14d8c5b49c832f4100f83b53fdc01f5108f7db11de38fd0ee6dbe5"


def load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def ansible_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"true", "yes", "1", "on"}


def render(overrides=None):
    variables = load(DEFAULTS)
    variables.update(load(EXAMPLE))
    variables.update(overrides or {})
    env = jinja2.Environment(undefined=jinja2.StrictUndefined, autoescape=False)
    env.filters["bool"] = ansible_bool
    return env.from_string(VALUES_TEMPLATE.read_text(encoding="utf-8")).render(**variables)


def test_pins_and_persistence_defaults():
    defaults = load(DEFAULTS)
    chart = load(CHART / "Chart.yaml")
    values = load(CHART / "values.yaml")
    assert chart["version"] == "0.1.0"
    assert chart["appVersion"] == "2026.10.5"
    assert defaults["openclaw_k8s_image_digest"] == DIGEST
    assert values["image"]["digest"] == DIGEST
    assert defaults["openclaw_k8s_replica_count"] == 1
    assert defaults["openclaw_k8s_strategy"] == "Recreate"
    assert defaults["openclaw_k8s_persistence_enabled"] is True
    assert defaults["openclaw_k8s_persistence_size"] == "10Gi"
    assert defaults["openclaw_k8s_persistence_access_mode"] == "ReadWriteOnce"


def test_defaults_fail_closed_and_require_inputs():
    defaults = load(DEFAULTS)
    validation = (ROLE / "tasks" / "validate-inputs.yml").read_text(encoding="utf-8")
    assert defaults["openclaw_k8s_exposure_enabled"] is False
    assert defaults["openclaw_k8s_gateway_bind"] == "loopback"
    assert defaults["openclaw_k8s_existing_secret"] == ""
    assert defaults["openclaw_k8s_storage_class"] == ""
    assert defaults["openclaw_k8s_live_checks"] is False
    assert defaults["openclaw_k8s_destroy_pvc"] is False
    for required in ("existing_secret", "storage_class", "kube_context"):
        assert required in validation


def test_example_enables_tailscale_only_exposure():
    example = load(EXAMPLE)
    assert example["openclaw_k8s_exposure_enabled"] is True
    assert example["openclaw_k8s_ingress_class_name"] == "tailscale"
    assert example["openclaw_k8s_gateway_bind"] == "lan"
    assert example["openclaw_k8s_tailnet_hostname"].endswith(".ts.net")
    assert example["openclaw_k8s_allowed_origins"] == [
        "https://" + example["openclaw_k8s_tailnet_hostname"]
    ]


def test_values_render_is_yaml_and_secret_reference_only():
    text = render()
    parsed = yaml.safe_load(text)
    assert parsed["existingSecret"] == "change-me-openclaw-secret"
    assert parsed["service"]["type"] == "ClusterIP"
    assert parsed["ingress"]["enabled"] is True
    assert parsed["gateway"]["authMode"] == "token"
    assert parsed["gateway"]["externalMessagingEnabled"] is False
    assert parsed["image"]["digest"] == DIGEST
    lower = text.lower()
    forbidden_markers = (
        "private key",
        "pass" + "word:",
        "bearer ",
        "sk-ant-",
        "sk-proj-",
    )
    for forbidden in forbidden_markers:
        assert forbidden not in lower


def test_chart_has_no_secret_or_cluster_wide_rbac_template():
    names = {p.name for p in (CHART / "templates").iterdir()}
    assert not any("secret" in name for name in names)
    assert not any("clusterrole" in name or "rolebinding" in name for name in names)
    deployment = (CHART / "templates" / "deployment.yaml").read_text(encoding="utf-8")
    service = (CHART / "templates" / "service.yaml").read_text(encoding="utf-8")
    ingress = (CHART / "templates" / "ingress.yaml").read_text(encoding="utf-8")
    assert "automountServiceAccountToken: false" in deployment
    assert "readOnlyRootFilesystem: true" in deployment
    assert "XDG_CACHE_HOME" in deployment
    assert "/startupz" in deployment
    assert "/healthz" in deployment
    assert "type: ClusterIP" in service
    assert "secretName" not in ingress


def test_public_exposure_keys_absent():
    blobs = [p.read_text(encoding="utf-8") for p in CHART.rglob("*") if p.is_file()]
    blob = "\n".join(blobs)
    for forbidden in ("NodePort", "LoadBalancer", "hostNetwork", "hostPath", "docker.sock", "privileged: true"):
        assert forbidden not in blob
    defaults = load(DEFAULTS)
    assert defaults["openclaw_k8s_funnel_enabled"] is False
    assert defaults["openclaw_k8s_external_messaging_enabled"] is False


def test_init_seeds_only_missing_files():
    deployment = (CHART / "templates" / "deployment.yaml").read_text(encoding="utf-8")
    assert re.search(r"\[ -f .*openclaw\.json \] \|\| cp", deployment)
    assert re.search(r"\[ -f .*AGENTS\.md \] \|\| cp", deployment)


def test_helm_rejects_missing_secret_and_public_service_type():
    helm = shutil.which("helm")
    if helm is None:
        return
    missing = subprocess.run(
        [helm, "template", "openclaw", str(CHART)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode != 0
    assert "existingSecret is required" in missing.stderr

    public = subprocess.run(
        [
            helm,
            "template",
            "openclaw",
            str(CHART),
            "--set",
            "existingSecret=example-openclaw-secret",
            "--set",
            "service.type=NodePort",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert public.returncode != 0
    assert "service.type must be ClusterIP" in public.stderr
