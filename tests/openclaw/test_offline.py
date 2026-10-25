from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import jinja2
import yaml

REPO = Path(__file__).resolve().parents[2]
ROLE = REPO / "roles" / "openclaw_k8s"
CHART = REPO / "charts" / "openclaw" / "0.2.1"
DEFAULTS = ROLE / "defaults" / "main.yml"
EXAMPLE = REPO / "inventory" / "example" / "group_vars" / "openclaw_k3s.yml"
VALUES_TEMPLATE = ROLE / "templates" / "values-openclaw.yml.j2"
DIGEST = "sha256:fb26f0841659dc757f23feec9adeab51f11d76779a409db5d22e191b43841afa"


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


def resolve_defaults(overrides=None, use_example=True):
    """Resolve the role defaults the way Ansible does.

    Role defaults may carry Jinja (the gateway bind depends on whether
    exposure is enabled), so the literal YAML value is not the contract --
    the RESOLVED value is. Evaluate them here rather than asserting on the
    unrendered string.
    """
    variables = load(DEFAULTS)
    if use_example:
        variables.update(load(EXAMPLE))
    variables.update(overrides or {})
    env = jinja2.Environment(undefined=jinja2.StrictUndefined, autoescape=False)
    env.filters["bool"] = ansible_bool
    env.filters["dirname"] = lambda p: os.path.dirname(str(p))
    env.filters["basename"] = lambda p: os.path.basename(str(p))
    env.filters["to_json"] = lambda v: json.dumps(v)
    resolved = {}
    for key, value in variables.items():
        if isinstance(value, str):
            try:
                resolved[key] = env.from_string(value).render(**variables)
            except Exception:
                # Not every default is templatable outside Ansible (some
                # reference role/playbook context). Those are irrelevant to the
                # contract under test; keep the literal.
                resolved[key] = value
        elif isinstance(value, list):
            items = []
            for v in value:
                if isinstance(v, str):
                    try:
                        v = env.from_string(v).render(**variables)
                    except Exception:
                        pass
                items.append(v)
            resolved[key] = items
        else:
            resolved[key] = value
    return resolved


def test_pins_and_persistence_defaults():
    defaults = load(DEFAULTS)
    chart = load(CHART / "Chart.yaml")
    values = load(CHART / "values.yaml")
    assert chart["version"] == "0.2.1"
    assert chart["appVersion"] == "2026.10.7"
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
    # The bind default is conditional: restrictive unless exposure is on.
    # Resolve the ROLE defaults alone: the example inventory pins bind=lan
    # explicitly, so merging it would mask the default's own behaviour.
    assert resolve_defaults({"openclaw_k8s_exposure_enabled": False},
                            use_example=False)["openclaw_k8s_gateway_bind"] == "loopback"
    assert resolve_defaults({"openclaw_k8s_exposure_enabled": True},
                            use_example=False)["openclaw_k8s_gateway_bind"] == "lan"
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


def test_tailnet_hostname_is_a_bare_hostspec_and_origin_is_the_fqdn():
    """The Control UI validates the browser's REAL origin.

    The operator mints the device from a bare hostspec and appends the tailnet
    domain itself, so the browser origin is
    https://<host>.<tailnetDomain> -- NOT https://<host>. Asserting the bare
    host let the UI load and then refuse every request.
    """
    example = load(EXAMPLE)
    host = example["openclaw_k8s_tailnet_hostname"]
    domain = example["openclaw_k8s_tailnet_domain"]
    assert "." not in host, "ingress host must be a bare hostspec, not an FQDN"
    assert domain and "." not in domain
    assert example["openclaw_k8s_allowed_origins"] == [
        "https://%s.%s" % (host, domain)
    ]


def test_role_defaults_derive_the_same_fqdn_origin():
    # Resolve the ROLE DEFAULTS alone. Merging the example inventory would
    # let it mask the default's own value, and the assertion would go
    # vacuous -- proven by mutation: an FQDN in the default went undetected.
    resolved = resolve_defaults(use_example=False)
    host = resolved["openclaw_k8s_tailnet_hostname"]
    domain = resolved["openclaw_k8s_tailnet_domain"]
    assert "." not in host, "the role default hostname must be a bare hostspec"
    assert "." in domain
    assert resolved["openclaw_k8s_allowed_origins"] == [
        "https://%s.%s" % (host, domain)
    ]


def test_chart_requires_the_fqdn_origin_not_the_bare_host():
    """The chart guard must reject the bare-host origin.

    Rendered with a bare-host origin, the template has to FAIL -- otherwise
    the Control UI rejects the real browser origin at run time.
    """
    helm = shutil.which("helm")
    if helm is None:
        return
    bad = subprocess.run(
        [
            helm, "template", "openclaw", str(CHART),
            "--set", "existingSecret=example-openclaw-secret",
            "--set", "ingress.enabled=true",
            "--set", "ingress.className=tailscale",
            "--set", "ingress.host=noesis-openclaw",
            "--set", "ingress.tailnetDomain=tailf99a0.ts.net",
            "--set", "gateway.bind=lan",
            "--set", "gateway.allowedOrigins[0]=https://noesis-openclaw",
        ],
        capture_output=True, text=True, check=False,
    )
    assert bad.returncode != 0
    assert "must include the exact browser origin" in bad.stderr

    good = subprocess.run(
        [
            helm, "template", "openclaw", str(CHART),
            "--set", "existingSecret=example-openclaw-secret",
            "--set", "ingress.enabled=true",
            "--set", "ingress.className=tailscale",
            "--set", "ingress.host=noesis-openclaw",
            "--set", "ingress.tailnetDomain=tailf99a0.ts.net",
            "--set", "gateway.bind=lan",
            "--set", "gateway.allowedOrigins[0]=https://noesis-openclaw.tailf99a0.ts.net",
        ],
        capture_output=True, text=True, check=False,
    )
    assert good.returncode == 0, good.stderr


def test_probe_contract_matches_the_upstream_json_keys():
    """Each probe must assert the key its own route returns.

    Upstream (src/gateway/server-http-probes.ts) returns
    /startupz -> {"ok": bool} and /readyz -> {"ready": bool}. Asserting
    `.ready` against /startupz is always false (the key is absent), which
    deadlocks the pod in a startup-probe failure loop.
    """
    deployment = (CHART / "templates" / "deployment.yaml").read_text(encoding="utf-8")
    startup = re.search(r"startupProbe:.*?/startupz.*?j\.(\w+)===true", deployment, re.S)
    readiness = re.search(r"readinessProbe:.*?/readyz.*?j\.(\w+)===true", deployment, re.S)
    liveness = re.search(r"livenessProbe:.*?/healthz.*?j\.(\w+)===true", deployment, re.S)
    assert startup and startup.group(1) == "ok", "startup probe must assert j.ok"
    assert readiness and readiness.group(1) == "ready", "readiness probe must assert j.ready"
    assert liveness and liveness.group(1) == "ok", "liveness probe must assert j.ok"
    # The readiness probe must not still point at /startupz.
    assert re.search(r"readinessProbe:.*?/readyz", deployment, re.S)


def test_reserved_hostnames_are_guarded():
    """A proxy device that claims an existing name hijacks that identity."""
    defaults = load(DEFAULTS)
    reserved = defaults["openclaw_k8s_reserved_hostnames"]
    assert "tailscale-operator" in reserved
    assert "noesis-lab" in reserved
    assert "noesis-praxis" in reserved
    assert defaults["openclaw_k8s_tailnet_hostname"] not in reserved
    validation = (ROLE / "tasks" / "validate-inputs.yml").read_text(encoding="utf-8")
    assert "openclaw_k8s_reserved_hostnames" in validation


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


def test_init_merges_chart_owned_config_keys():
    """The seed must MERGE the chart-owned keys, not only seed a missing file.

    Copying the seed only when openclaw.json is absent means a settings
    change never reaches a running gateway: the file already exists on the
    PVC, so the new seed is ignored and the change silently does nothing.
    Overwriting the whole file instead would discard app-owned state
    (channels, agents), so only the chart-owned top-level keys are replaced.
    """
    deployment = (CHART / "templates" / "deployment.yaml").read_text(encoding="utf-8")
    assert 'const OWNED = ["gateway", "cron"]' in deployment
    assert 'live[key] = seed[key]' in deployment
    assert "node --input-type=commonjs" in deployment
    # The whole-file seed must be GONE -- it is what swallowed the change.
    assert not re.search(r"\[ -f .*openclaw\.json \] \|\| cp", deployment)
    # AGENTS.md is workspace content, not chart-owned config: still seed-once.
    assert re.search(r"\[ -f .*AGENTS\.md \] \|\| cp", deployment)


def test_config_change_rolls_the_pod():
    """A config change must roll the pod, or it never reaches the gateway."""
    deployment = (CHART / "templates" / "deployment.yaml").read_text(encoding="utf-8")
    assert "checksum/config:" in deployment
    assert "configmap.yaml" in deployment
    assert "sha256sum" in deployment


def test_trusted_proxies_is_rendered_when_set():
    """The gateway fails closed on proxy-shaped traffic from an untrusted
    source, so a Tailscale-Ingress deployment must declare the proxy."""
    helm = shutil.which("helm")
    if helm is None:
        return
    out = subprocess.run(
        [
            helm, "template", "openclaw", str(CHART),
            "--set", "existingSecret=example-openclaw-secret",
            "--set", "gateway.trustedProxies[0]=10.42.0.0/24",
        ],
        capture_output=True, text=True, check=False,
    )
    assert out.returncode == 0, out.stderr
    assert '"trustedProxies": ["10.42.0.0/24"]' in out.stdout

    # And it must be absent (not rendered as an empty array) when unset.
    bare = subprocess.run(
        [helm, "template", "openclaw", str(CHART),
         "--set", "existingSecret=example-openclaw-secret"],
        capture_output=True, text=True, check=False,
    )
    assert bare.returncode == 0, bare.stderr
    assert "trustedProxies" not in bare.stdout


def test_chart_version_is_bumped_so_the_upgrade_applies():
    """The Helm module skips an upgrade when the chart VERSION is unchanged.

    Editing chart content without bumping the version makes the run report
    ok/changed=0 and leaves the release on the old chart -- the change is
    silently dropped. Pin the chart version here so a content edit without a
    version bump fails the suite.
    """
    defaults = load(DEFAULTS)
    chart = load(CHART / "Chart.yaml")
    validation = (ROLE / "tasks" / "validate-inputs.yml").read_text(encoding="utf-8")
    assert chart["version"] == defaults["openclaw_k8s_chart_version"]
    assert defaults["openclaw_k8s_chart_version"] == "0.2.1"
    assert "openclaw_k8s_chart_version == '0.2.1'" in validation
    # The chart DIRECTORY name must match the version helm records.
    assert CHART.name == chart["version"]


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


def test_host_role_installs_via_the_vendor_installer():
    role = REPO / "roles" / "openclaw_host"
    defaults = load(role / "defaults" / "main.yml")
    tasks = (role / "tasks" / "main.yml").read_text(encoding="utf-8")
    assert defaults["openclaw_host_install_url"] == "https://openclaw.ai/install.sh"
    assert defaults["openclaw_host_version"] == "2026.10.7"
    assert defaults["openclaw_host_live_changes"] is False
    assert defaults["openclaw_host_gateway_bind"] == "loopback"
    # The credential is never generated or inlined by the role. The NAME may
    # appear in comments and error messages; what must not appear is a task
    # that ASSIGNS a literal token value.
    assert "openclaw_host_env_file" in defaults
    assert "openclaw_host_envfile_stat" in tasks
    # No hardcoded secret: nothing that looks like a generated token literal.
    assert not re.search(r"[0-9a-f]{32,}", tasks), "a token literal leaked into the role"
    assert not re.search(r"OPENCLAW_GATEWAY_TOKEN\s*[:=]\s*[\"\']?(?!<|\{\{)\S", tasks)
    # Live work must be opt-in.
    assert "openclaw_host_live_changes | bool" in tasks


def test_host_role_renders_valid_json_and_unit():
    role = REPO / "roles" / "openclaw_host"
    template = (role / "templates" / "openclaw.json.j2").read_text(encoding="utf-8")
    # JSON has no comment syntax and no YAML document marker.
    assert not template.lstrip().startswith("---")
    assert not template.lstrip().startswith("#")
    unit = (role / "templates" / "openclaw-gateway.service.j2").read_text(encoding="utf-8")
    assert "EnvironmentFile=" in unit
    assert "ExecStart=" in unit


def test_docker_role_uses_the_digest_pinned_image():
    role = REPO / "roles" / "openclaw_docker"
    defaults = load(role / "defaults" / "main.yml")
    assert defaults["openclaw_docker_image_digest"] == DIGEST
    assert defaults["openclaw_docker_image_tag"] == "2026.10.7-slim"
    assert defaults["openclaw_docker_live_changes"] is False
    # A list, not a string: `first`/`join` on a string yields characters.
    assert isinstance(defaults["openclaw_docker_compose_cmd"], list)
    assert defaults["openclaw_docker_compose_cmd"] == ["docker", "compose"]
    compose = (role / "templates" / "compose.yaml.j2").read_text(encoding="utf-8")
    # The upstream compose file builds from source; this one uses the pin.
    # Match an actual YAML key, not the word inside an explanatory comment.
    assert not re.search(r"^\s*build:", compose, re.M)
    assert "image.digest" in compose or "openclaw_docker_image" in compose


def test_deploy_playbook_dispatches_all_three_methods():
    playbook = (REPO / "playbooks" / "openclaw-deploy.yml").read_text(encoding="utf-8")
    for method in ("host", "docker", "k8s"):
        assert "openclaw_deploy_method == '%s'" % method in playbook
    for role in ("openclaw_host", "openclaw_docker", "openclaw_k8s"):
        assert "name: %s" % role in playbook


def test_alphaclaw_role_is_untouched():
    """roles/openclaw deploys AlphaClaw, a DIFFERENT product.

    It must not be mistaken for upstream OpenClaw and rewritten.
    """
    legacy = load(REPO / "roles" / "openclaw" / "defaults" / "main.yml")
    assert legacy["openclaw_image"] == "garrytan/alphaclaw:latest"
    assert legacy["openclaw_port"] == 8090


def test_chart_refuses_a_reserved_hostname():
    """A proxy that claims an existing device name hijacks that identity."""
    helm = shutil.which("helm")
    if helm is None:
        return
    for reserved in ("noesis-lab", "noesis-praxis", "tailscale-operator"):
        out = subprocess.run(
            [
                helm, "template", "openclaw", str(CHART),
                "--set", "existingSecret=example-openclaw-secret",
                "--set", "ingress.enabled=true",
                "--set", "ingress.className=tailscale",
                "--set", "ingress.host=%s" % reserved,
                "--set", "ingress.tailnetDomain=tailf99a0.ts.net",
                "--set", "ingress.reservedHostnames[0]=tailscale-operator",
                "--set", "ingress.reservedHostnames[1]=noesis-praxis",
                "--set", "ingress.reservedHostnames[2]=noesis-lab",
                "--set", "gateway.bind=lan",
                "--set", "gateway.allowedOrigins[0]=https://x.tailf99a0.ts.net",
            ],
            capture_output=True, text=True, check=False,
        )
        assert out.returncode != 0, "chart accepted reserved hostname %s" % reserved
        assert "is reserved" in out.stderr, out.stderr


def test_standalone_playbooks_load_the_role_defaults():
    """The standalone playbooks do not declare the role.

    Without the role's defaults in scope they die on an undefined
    target-side Python venv path before doing anything.
    """
    for name in ("openclaw-k8s-verify.yml", "openclaw-k8s-preflight.yml",
                 "openclaw-k8s-remove.yml", "openclaw-k8s-secret.yml"):
        text = (REPO / "playbooks" / name).read_text(encoding="utf-8")
        assert "vars_files:" in text, "%s does not load the role defaults" % name
        assert "roles/openclaw_k8s/defaults/main.yml" in text, name


if __name__ == "__main__":
    # A pytest-style suite with no runner is a SILENT NO-OP when executed as a
    # script -- it exits 0 having asserted nothing. Run the checks here so the
    # suite is meaningful in the repo's plain-`python3` convention.
    import sys
    import traceback

    checks = [(n, f) for n, f in sorted(globals().items())
              if n.startswith("test_") and callable(f)]
    failures = []
    for name, fn in checks:
        try:
            fn()
            print("  ok   %s" % name)
        except Exception:
            failures.append(name)
            print("  FAIL %s" % name)
            traceback.print_exc()
    print("\npassed: %d   failed: %d" % (len(checks) - len(failures), len(failures)))
    if failures:
        print("failed checks: %s" % ", ".join(failures))
        sys.exit(1)
    print("OFFLINE VALIDATION PASSED")
