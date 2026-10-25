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
CHART = REPO / "charts" / "openclaw" / "0.3.2"
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
    assert chart["version"] == "0.3.2"
    assert chart["appVersion"] == "2026.10.7"
    assert defaults["openclaw_k8s_image_digest"] == DIGEST
    assert values["image"]["digest"] == DIGEST
    assert defaults["openclaw_k8s_replica_count"] == 1
    assert defaults["openclaw_k8s_strategy"] == "Recreate"
    assert defaults["openclaw_k8s_persistence_enabled"] is True
    assert defaults["openclaw_k8s_persistence_size"] == "10Gi"
    assert defaults["openclaw_k8s_persistence_access_mode"] == "ReadWriteOnce"


def test_gateway_resource_envelope_allows_worker_pool_startup():
    """The gateway container needs room for its worker fan-out.

    It was OOMKilled at the previous 2Gi limit: RSS climbed from ~400Mi to
    the ceiling within ~90s of start-up, so the pod never reached Ready and
    the Tailscale Ingress returned 502. The Node's own diagnostics attribute
    the pressure to 16 worker threads (~854MiB of worker heap) rather than
    the main heap (~295MiB). Pin the envelope so a future edit that silently
    shrinks it fails here instead of in production.
    """
    values = load(CHART / "values.yaml")
    limits = values["resources"]["limits"]
    requests = values["resources"]["requests"]
    assert limits["memory"] == "4Gi"
    assert limits["cpu"] == "2"
    # Burstable: requests must stay below limits, or the pod reserves the
    # whole envelope and can starve other workloads on the single node.
    assert requests["memory"] == "1Gi"
    assert requests["cpu"] == "500m"


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
    # The owned set must cover every chart-owned block: a key that is not
    # owned is never replaced, so a change to it silently does nothing.
    assert 'const OWNED = ["gateway", "cron", "plugins", "agents"]' in deployment
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
    assert defaults["openclaw_k8s_chart_version"] == "0.3.2"
    assert "openclaw_k8s_chart_version == '0.3.2'" in validation
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


def test_escrow_task_captures_the_token_through_a_pty():
    """The CLI refuses to print the token outside an interactive terminal.

    It checks BOTH stdin.isTTY and stdout.isTTY, so a plain pipe yields
    nothing. The capture must therefore allocate a pty INSIDE the container
    (where the CLI runs) and must never let the token reach stdout of the
    Ansible task.
    """
    escrow_path = ROLE / "tasks" / "escrow_authtoken.yml"
    escrow = escrow_path.read_text(encoding="utf-8")
    assert "doctor" in escrow and "--generate-gateway-token" in escrow

    # EVERY capture must go through the pty wrapper, not a bare exec. A
    # file-level string check is vacuous: a second capture elsewhere in the
    # file keeps "script" present while one call regresses to a bare exec.
    tasks = yaml.safe_load(escrow)
    captures = []

    def collect(node):
        for task in node:
            argv = task.get("ansible.builtin.command", {}).get("argv") or []
            # Match on the CLI ENTRYPOINT. Matching "auth-token --show" in a
            # single element would miss a bare exec that splits the command
            # across elements -- exactly the regression this test must catch.
            # A --note that merely quotes the command name has no
            # dist/index.js and is not a capture.
            is_cli = any("dist/index.js" in str(a) for a in argv)
            # `doctor --generate-gateway-token` also runs the CLI but does not
            # print the token, so it needs no pty. Only the SHOW command does.
            shows_token = any("auth-token" in str(a) for a in argv)
            if is_cli and shows_token:
                captures.append(argv)
            for member in task.get("block") or []:
                collect([member])

    collect(tasks)
    assert captures, "no capture invocation found"
    for argv in captures:
        assert "script" in argv, argv
        assert "-qec" in argv, argv
        assert any("auth-token" in str(a) for a in argv), argv


def test_every_token_task_is_no_log():
    """A token must never reach the transcript."""
    escrow_path = ROLE / "tasks" / "escrow_authtoken.yml"
    tasks = yaml.safe_load(escrow_path.read_text(encoding="utf-8"))
    assert tasks, "no tasks found"

    def check(node):
        """Every task that handles the token VALUE must be no_log."""
        for task in node:
            name = str(task.get("name", ""))
            if "block:" not in task and "block" not in task:
                if any(k in name for k in ("token", "Token")):
                    # A report that deliberately reveals only metadata (the
                    # escrow KEY and the token LENGTH) is safe, and no_log
                    # would only hide it.
                    if "without revealing the token" not in name:
                        assert task.get("no_log") is True, name
            for member in task.get("block") or []:
                check([member])

    check(tasks)


def test_escrow_task_uses_the_kubeconfig_on_every_kubectl_call():
    """A kubectl call without --kubeconfig fails in a non-interactive run.

    That failure is silent under `failed_when: false` and then surfaces as
    "the Gateway has no token" -- a completely different fault with a
    different remedy.
    """
    escrow = (ROLE / "tasks" / "escrow_authtoken.yml").read_text(encoding="utf-8")
    # Count only ARGV-form invocations -- the same variable also appears as a
    # stat() path and inside a failure message.
    kubectl_calls = escrow.count('- "{{ openclaw_k8s_kubectl_binary_path }}"')
    assert kubectl_calls >= 4, "expected several kubectl invocations"
    assert escrow.count("--kubeconfig") == kubectl_calls
    assert escrow.count("--context") == kubectl_calls


def test_escrow_asserts_the_secret_matches_the_gateway():
    """The escrow and the delivered Secret must not drift apart."""
    escrow = (ROLE / "tasks" / "escrow_authtoken.yml").read_text(encoding="utf-8")
    assert "Assert the delivered Secret carries the Gateway's own auth-token" in escrow
    assert "b64decode" in escrow
    # A capture failure must not masquerade as "no token".
    assert "Distinguish a capture failure from an absent token" in escrow


def test_kubectl_binary_default_exists_on_this_host():
    """The role uses kubectl as a real binary, not just as a module hint.

    A wrong default stayed invisible because the only preflight path that
    used it as a binary (namespace absent) never ran.
    """
    defaults = load(DEFAULTS)
    path = defaults["openclaw_k8s_kubectl_binary_path"]
    assert os.path.isfile(path), "%s does not exist on this host" % path
    assert os.access(path, os.X_OK), "%s is not executable" % path


def test_secret_playbook_sources_the_escrowed_token():
    secret = (REPO / "playbooks" / "openclaw-k8s-secret.yml").read_text(encoding="utf-8")
    defaults = load(DEFAULTS)
    assert defaults["openclaw_k8s_authtoken_escrow_key"] in secret
    # The delivered key must be the one the Gateway reads.
    assert defaults["openclaw_k8s_authtoken_secret_key"] in secret


def test_device_playbook_actions_are_gated():
    """Device pairing grants gateway access -- gate it explicitly."""
    device = (REPO / "playbooks" / "openclaw-k8s-device.yml").read_text(encoding="utf-8")
    for action in ("list", "approve", "approve-latest", "reject"):
        assert action in device
    assert "openclaw_device_request_id" in device
    # approve/reject must not be reachable without an explicit request id.
    assert "openclaw_device_action not in ['approve', 'reject'] or openclaw_device_request_id | length > 0" in device
    # The commands run inside the pod, where the CLI and pairing state live.
    assert "dist/index.js" in device and "devices" in device
    assert "--kubeconfig" in device





# --- typesafe plugin, credential and decision model ------------------------


def helm_render(chart=CHART, extra=None):
    args = ["helm", "template", "openclaw", str(chart), "--namespace", "openclaw",
            "--set", "existingSecret=openclaw-secrets"]
    for kv in extra or []:
        args += ["--set", kv]
    out = subprocess.run(args, capture_output=True, text=True)
    assert out.returncode == 0, "helm template failed:\n%s" % out.stderr
    return out.stdout


def rendered_config():
    docs = [d for d in yaml.safe_load_all(helm_render()) if d]
    cm = [d for d in docs if d.get("kind") == "ConfigMap"][0]
    return json.loads(cm["data"]["openclaw.json"])


def rendered_deployment():
    """The rendered Deployment as TEXT -- assertions on values must see the VALUES.

    Asserting against the template source only proves the template mentions a
    thing; the placeholder decides what it actually becomes. The text is kept
    raw (not re-dumped as YAML) because a re-dump wraps long shell commands
    across lines and breaks substring matching on the command itself.
    """
    for chunk in helm_render().split("\n---\n"):
        if "kind: Deployment" in chunk:
            return chunk
    raise AssertionError("the rendered chart has no Deployment")


def rendered_deployment_obj():
    docs = [d for d in yaml.safe_load_all(helm_render()) if d]
    return [d for d in docs if d.get("kind") == "Deployment"][0]


def init_container(name):
    spec = rendered_deployment_obj()["spec"]["template"]["spec"]
    for c in spec.get("initContainers", []):
        if c["name"] == name:
            return c
    raise AssertionError("no init container named %s" % name)


def command_lines(text):
    """Shell lines only -- comments mention forbidden options by name."""
    return "\n".join(l for l in text.splitlines()
                      if not l.strip().startswith("#"))


def test_rendered_config_is_valid_json():
    """The seeded config must PARSE.

    A missing comma between the plugin and agent entries rendered a
    syntactically invalid openclaw.json that only failed when the Gateway
    tried to read it.
    """
    cfg = rendered_config()
    assert isinstance(cfg, dict) and "gateway" in cfg


def test_rendered_config_carries_the_typesafe_plugin_block():
    cfg = rendered_config()
    plugins = cfg["plugins"]
    assert plugins["allow"] == ["typesafe"]
    entry = plugins["entries"]["typesafe"]
    assert entry["enabled"] is True
    # The credential must be a SecretRef into the store -- never a literal.
    api_key = entry["config"]["apiKey"]
    assert api_key == {"source": "store", "provider": "default", "id": "TYPESAFE_API_KEY"}


def test_rendered_config_carries_the_decision_models():
    cfg = rendered_config()
    agents = cfg["agents"]
    assert agents["ownership"] == "explicit"
    assert agents["defaults"]["decisionModel"] == "typesafe/jev-latest"
    assert agents["entries"]["research"]["decisionModel"] == "typesafe/jev-1.13.0"
    # With explicit ownership and several agents, an unnamed system agent
    # breaks every owner-scoped command ("model inspection has no explicit
    # owner").
    assert agents["defaults"]["systemAgent"]["agentId"] == "default"


def test_agents_block_has_no_heartbeat_owner():
    """Heartbeats stay disabled: they need their own agentId.

    The chart disables automations (cron); enabling a heartbeat owner would
    start background work nobody asked for.
    """
    cfg = rendered_config()
    assert "heartbeat" not in cfg["agents"]["defaults"]
    assert cfg["cron"]["enabled"] is False


def test_the_plugin_is_installed_by_the_init_container():
    deployment = rendered_deployment()
    assert "plugins install" in deployment
    assert "@openclaw/typesafe@2026.10.7" in deployment


def test_the_plugin_install_is_skipped_when_already_registered():
    """The skip test must consult the persisted registry, not a path.

    The install layout differs per package (managed npm project vs
    extensions/), so a path check would re-install on every pod start.
    """
    deployment = rendered_deployment()
    assert "plugins list --json" in deployment
    assert 'grep -q \'"id": "typesafe"\'' in deployment


def test_the_secret_store_write_never_puts_the_value_in_argv():
    """`secrets store set --value` is REFUSED for secret-kind entries.

    The value must arrive through --value-file so it never appears in argv
    (visible in /proc and in any process listing).
    """
    deployment = command_lines(rendered_deployment())
    assert "secrets store set TYPESAFE_API_KEY --value-file -" in deployment
    # The value must never be an argument.
    assert "--value " not in deployment
    assert "--value=" not in deployment
    # It arrives through the environment, not through the command line.
    assert "printenv TYPESAFE_API_KEY |" in deployment


def test_the_temp_root_is_prepared_for_the_plugin_installer():
    """The plugin installer refuses a group/world-writable temp root.

    The emptyDir that backs /tmp is created 2777 and the container runs as
    uid 1000, so it cannot restore the sticky bit itself -- /tmp is
    root-owned. A root init container restores 1777 and nothing else.
    """
    deployment = (CHART / "templates" / "deployment.yaml").read_text(encoding="utf-8")
    assert "chmod 1777 /tmp" in deployment
    assert "prepare-temp" in deployment


def test_the_root_init_container_is_otherwise_unprivileged():
    container = init_container("prepare-temp")
    sc = container["securityContext"]
    assert sc["runAsUser"] == 0
    assert sc["readOnlyRootFilesystem"] is True
    assert sc["allowPrivilegeEscalation"] is False
    assert sc["capabilities"]["drop"] == ["ALL"]
    # It must do the chmod and nothing else.
    script = "\n".join(command_lines(container["command"][-1]).splitlines())
    chmods = [l.strip() for l in script.splitlines() if l.strip().startswith("chmod")]
    assert len(chmods) == 1, "prepare-temp must do the chmod and nothing else"
    assert chmods[0].endswith("1777 /tmp")


def test_the_seed_init_container_runs_unprivileged_with_the_secret_env():
    container = init_container("seed-config")
    assert container["securityContext"]["runAsUser"] == 1000
    # The secret value arrives as an environment variable from the Secret.
    assert container["envFrom"][0]["secretRef"]["name"]
    # npm's cache must not land on the read-only rootfs.
    env = {e["name"]: e.get("value") for e in container["env"]}
    assert env["npm_config_cache"].startswith("/home/node/.openclaw/")


def test_the_role_defaults_pin_the_typesafe_plugin():
    defaults = load(DEFAULTS)
    installs = defaults["openclaw_k8s_plugins_install"]
    assert len(installs) == 1
    assert installs[0]["id"] == "typesafe"
    assert installs[0]["spec"].startswith("@openclaw/typesafe@")
    assert defaults["openclaw_k8s_plugins_allow"] == ["typesafe"]
    api_key = defaults["openclaw_k8s_plugins_entries"]["typesafe"]["config"]["apiKey"]
    assert api_key["id"] == "TYPESAFE_API_KEY"
    assert api_key["source"] == "store"
    assert defaults["openclaw_k8s_secret_store_entries"][0]["name"] == "TYPESAFE_API_KEY"


def test_the_role_renders_the_plugin_and_agent_blocks():
    values = yaml.safe_load(render())
    assert values["plugins"]["allow"] == ["typesafe"]
    assert values["plugins"]["install"][0]["id"] == "typesafe"
    assert values["agents"]["defaults"]["decisionModel"] == "typesafe/jev-latest"
    assert values["agents"]["defaults"]["systemAgent"]["agentId"] == "default"
    assert values["secretStore"]["entries"][0]["name"] == "TYPESAFE_API_KEY"


def test_the_secret_playbook_delivers_the_typesafe_credential():
    secret = (REPO / "playbooks" / "openclaw-k8s-secret.yml").read_text(encoding="utf-8")
    assert "TYPESAFE_API_KEY" in secret


def test_the_config_merge_owns_the_plugin_and_agent_blocks():
    """A merge that does not own a key silently ignores changes to it."""
    deployment = (CHART / "templates" / "deployment.yaml").read_text(encoding="utf-8")
    match = re.search(r"const OWNED = \[([^\]]*)\]", deployment)
    assert match, "the config merge no longer declares its owned keys"
    owned = match.group(1)
    for key in ("plugins", "agents"):
        assert '"%s"' % key in owned


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
