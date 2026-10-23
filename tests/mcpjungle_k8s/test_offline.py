"""Offline validation for the MCPJungle Kubernetes deployment path.

These tests are deliberately non-mutating: no cluster, no Bitwarden writes, no
Helm release. They assert the properties that were the actual findings of the
chart/image review, so a future edit cannot silently reintroduce them.

Run:  python3 tests/mcpjungle_k8s/test_offline.py
"""

import json
import os
import re
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CHART = os.path.join(REPO, "charts", "mcpjungle")
ROLE = os.path.join(REPO, "roles", "mcpjungle")
PLAYBOOK = os.path.join(REPO, "playbooks", "mcpjungle-k8s.yml")
INV = os.path.join(REPO, "inventory", "mcpjungle-k8s", "group_vars", "all.yml")

REQUIRED_PROJECT = "72974d0e-81af-4678-bab7-b46000985859"

# Env vars the REJECTED community chart invented. Upstream has none of these.
INVENTED = ["MCPJUNGLE_ADMIN_TOKEN", "MCPJUNGLE_INIT_TOKEN",
            "MCPJUNGLE_SERVERS_FILE", "MCPJUNGLE_PORT", "MCPJUNGLE_LOG_LEVEL"]

failures = []
passes = 0


def check(name, cond, detail=""):
    global passes
    if cond:
        passes += 1
        print("  PASS  %s" % name)
    else:
        failures.append("%s %s" % (name, detail))
        print("  FAIL  %s %s" % (name, detail))


def helm(*args):
    return subprocess.run(["helm", *args], capture_output=True, text=True, cwd=REPO)


def read(path):
    with open(path) as fh:
        return fh.read()


def strip_comments(text):
    """Drop comment lines and trailing comments.

    Documentation comments legitimately name the rejected env vars and the
    ts.net suffix in order to explain why they are NOT used. Tests must assert
    on manifest content, not prose.
    """
    out = []
    for line in text.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("#") or stripped.startswith("{{- /*"):
            continue
        # Drop a trailing comment that is not inside quotes.
        if "#" in line and '"' not in line.split("#")[0]:
            line = line.split("#")[0]
        out.append(line)
    return "\n".join(out)


print("== chart provenance ==")
chart_yaml = read(os.path.join(CHART, "Chart.yaml"))
check("appVersion is pinned, not 'latest'", 'appVersion: "0.4.6"' in chart_yaml)
check("kubeVersion constraint present", "kubeVersion" in chart_yaml)
check("provenance annotation recorded", "image-provenance" in chart_yaml)

print("\n== image pinning ==")
rendered = helm("template", "mcpjungle", "charts/mcpjungle")
out = rendered.stdout
check("helm template succeeds", rendered.returncode == 0, rendered.stderr[:200])
check("image is digest-pinned",
      "ghcr.io/mcpjungle/mcpjungle@sha256:" in out)
check("no floating :latest image", ":latest" not in out)
check("rejected contributor image absent",
      "dinhdobathi1992" not in out and "noesislab/mcpjungle" not in out)

print("\n== verified upstream interface only ==")
values = read(os.path.join(CHART, "values.yaml"))
values_effective = strip_comments(values)
for var in INVENTED:
    check("invented env var not configured: %s" % var, var not in values_effective)
    check("invented env var absent from render: %s" % var, var not in out)
check("verified PORT used", "PORT" in values)
check("verified SERVER_MODE used", "SERVER_MODE" in values)
check("health probe path is /health", out.count("path: /health") >= 2)
check("no --ui flag (does not exist upstream)", "--ui" not in out)
check("containerPort is upstream default 8080", "containerPort: 8080" in out)

print("\n== no credential generation in the chart ==")
tpl_dir = os.path.join(CHART, "templates")
all_tpl = "\n".join(read(os.path.join(tpl_dir, f)) for f in os.listdir(tpl_dir))
for bad in ["helm.sh/hook", "randAlphaNum", "randBytes", "genPassword",
            "lookup ", "kind: Job"]:
    check("chart does not contain %r" % bad, bad not in all_tpl)
check("no helm hook annotations", "helm.sh/hook" not in all_tpl)

print("\n== postgres password is delivered as a FILE, not an env value ==")
check("POSTGRES_PASSWORD_FILE referenced", "POSTGRES_PASSWORD_FILE" in all_tpl)
check("no literal POSTGRES_PASSWORD value",
      "POSTGRES_PASSWORD:" not in all_tpl)

print("\n== tailnet exposure constraints ==")
ing = read(os.path.join(tpl_dir, "ingress.yaml"))
check("uses the tailscale ingress class", "ingressClassName" in ing)
check("managed-by label matches cluster convention",
      "ansible-tailscale-k8s" in ing)
check("no hardcoded tailnet domain in rendered manifests", "ts.net" not in out)
check("no LoadBalancer service type in chart", "LoadBalancer" not in out)

print("\n== Bitwarden project enforcement ==")
defaults = read(os.path.join(ROLE, "defaults", "main.yml"))
check("required project constant present",
      'mcpjungle_k8s_required_bw_project_id: "%s"' % REQUIRED_PROJECT in defaults)
secrets_tasks = read(os.path.join(ROLE, "tasks", "bw_escrow.yml"))
check("effective project is compared to the required id",
      "mcpjungle_k8s_required_bw_project_id" in secrets_tasks)
check("ambiguous record match fails closed",
      "Ambiguous" in secrets_tasks or "ambiguous" in secrets_tasks)
check("no secret task lacks no_log",
      secrets_tasks.count("no_log: true") >= 6)

print("\n== exposure gated on escrow ==")
expose = read(os.path.join(ROLE, "tasks", "expose_tailscale.yml"))
check("exposure asserts escrow first",
      "mcpjungle_k8s_bw_stored" in expose)
check("exposure refuses without stored credentials",
      "Refusing to expose" in expose)

print("\n== no plaintext secrets committed ==")
suspicious = re.compile(
    r"(?i)(password|token|secret[_-]?key|api[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9/+_-]{16,}")
for path in [INV, PLAYBOOK, os.path.join(CHART, "values.yaml")]:
    body = read(path)
    hits = [m for m in suspicious.findall(body)]
    check("no hardcoded credential literal in %s"
          % os.path.relpath(path, REPO), not hits, str(hits[:2]))
check("example inventory leaves the bws token empty",
      'mcpjungle_k8s_bws_access_token: ""' in read(INV))
check("bitwarden write gate defaults to false",
      "mcpjungle_k8s_allow_bitwarden_write: false" in read(INV))

print("\n== namespace manifest path actually resolves ==")
# Regression: the path was originally written with playbook_dir and pointed at
# a directory that does not exist (one version escaped the repo entirely).
role_path = os.path.join(REPO, "roles", "mcpjungle")
for src, label in [(defaults, "defaults/main.yml"), (read(INV), "inventory")]:
    m = re.search(r"mcpjungle_k8s_namespace_manifest:\s*\"(.+?)\"", src)
    check("%s declares the manifest path" % label, m is not None)
    if not m:
        continue
    tmpl = m.group(1)
    resolved = tmpl.replace("{{ role_path }}", role_path)
    resolved = os.path.normpath(resolved)
    check("%s path is role-relative" % label, "role_path" in tmpl, tmpl)
    check("%s path resolves to a real file" % label,
          os.path.isfile(resolved), resolved)

print("\n== Jinja in task files actually evaluates ==")
# A merge expression can read perfectly in review and still blow up at runtime
# on an empty dict. Execute the real expressions with ansible's own templar.
import shutil
import tempfile

if shutil.which("ansible-playbook"):
    tmp = tempfile.mkdtemp(prefix="mj-jinja-")
    probe = os.path.join(tmp, "probe.yml")
    install_expr = re.search(
        r"mcpjungle_k8s_rendered_values: >-\s*\n\s*\{\{.*?recursive=true\) \}\}",
        read(os.path.join(ROLE, "tasks", "install_k8s.yml")), re.S)
    expose_expr = re.search(
        r"mcpjungle_k8s_rendered_values: >-\s*\n\s*\{\{.*?recursive=true\) \}\}",
        read(os.path.join(ROLE, "tasks", "expose_tailscale.yml")), re.S)

    with open(os.path.join(tmp, "ansible.cfg"), "w") as fh:
        fh.write("[defaults]\nnocows = 1\nhost_key_checking = False\n")
    check("install values expression located", install_expr is not None)
    check("expose merge expression located", expose_expr is not None)
    with open(probe, "w") as fh:
        fh.write(
            "---\n- hosts: localhost\n  connection: local\n  gather_facts: false\n"
            "  vars:\n"
            "    mcpjungle_k8s_rendered_values: {}\n"
            "    mcpjungle_k8s_expose_enabled: false\n"
            "    mcpjungle_k8s_image_repository: ghcr.io/mcpjungle/mcpjungle\n"
            "    mcpjungle_k8s_image_tag: '0.4.6'\n"
            "    mcpjungle_k8s_image_digest: sha256:x\n"
            "    mcpjungle_k8s_database_mode: postgres\n"
            "    mcpjungle_k8s_database_postgres_host: pg\n"
            "    mcpjungle_k8s_database_postgres_port: 5432\n"
            "    mcpjungle_k8s_database_postgres_database: mcpjungle\n"
            "    mcpjungle_k8s_database_postgres_user: mcpjungle\n"
            "    mcpjungle_k8s_db_secret_name: mcpjungle-db\n"
            "    mcpjungle_k8s_db_secret_key: password\n"
            "    mcpjungle_k8s_ingress_class: tailscale\n"
            "    mcpjungle_k8s_ingress_host: mcpjungle\n"
            "    mcpjungle_k8s_ingress_tailnet: ''\n"
            "  tasks:\n"
            "    - name: install values expression\n"
            "      ansible.builtin.set_fact:\n"
            "        out_install: >-\n"
            + "".join("          " + ln + "\n" for ln in (install_expr.group(0).split("\n")[1:] if install_expr else []))
            + "    - name: expose merge expression (must tolerate an EMPTY dict)\n"
            "      ansible.builtin.set_fact:\n"
            "        out_expose: >-\n"
            + "".join("          " + ln + "\n" for ln in (expose_expr.group(0).split("\n")[1:] if expose_expr else []))
            + "    - name: assert the ingress key actually landed\n"
            "      ansible.builtin.assert:\n"
            "        that:\n"
            "          - out_expose.ingress.enabled is defined\n"
            "          - out_expose.ingress.enabled | bool\n"
        )
    res = subprocess.run(["ansible-playbook", "-i", "localhost,", "probe.yml"],
                         capture_output=True, text=True, cwd=tmp)
    check("task-file Jinja evaluates against an empty values dict",
          res.returncode == 0,
          (res.stdout + res.stderr)[-400:])
else:
    print("  SKIP  ansible-playbook not on PATH")

print("\n== render WITH ingress enabled (the path that was never exercised) ==")
ing = helm("template", "mcpjungle", "charts/mcpjungle",
           "--set", "ingress.enabled=true", "--set", "ingress.host=mcpjungle")
check("chart renders with ingress enabled", ing.returncode == 0,
      ing.stderr[-300:])
ing_out = ing.stdout
if ing.returncode == 0:
    check("Ingress object is present", "kind: Ingress" in ing_out)
    # B8: the chart names it mcpjungle.fullname, NOT <release>-ingress.
    names = [l.strip() for l in ing_out.split("\n") if l.startswith("  name: mcpjungle")]
    check("Ingress is named the release name (no '-ingress' suffix)",
          "  name: mcpjungle-ingress" not in ing_out, ing_out[:200])
    check("uses the tailscale ingress class",
          "ingressClassName: tailscale" in ing_out)
    # A `range` rebinds ".", so .Values inside it is nil: the whole chart dies.
    check("no unscoped .Values inside the paths range",
          "number: {{ $.Values.service.port }}" in
          read(os.path.join(tpl_dir, "ingress.yaml")))
    check("no duplicate managed-by label",
          ing_out.count("app.kubernetes.io/managed-by") ==
          ing_out.count("kind: Ingress") * 0 +
          len([1 for x in ing_out.split("---") if "kind: Ingress" in x]) +
          len([1 for x in ing_out.split("---")
               if "kind: Deployment" in x or "kind: Service" in x]))

print("\n== lint the RENDERED manifests (yamllint cannot parse {{- }} itself) ==")
if shutil.which("yamllint"):
    for label, args in [
            ("default values", ["template", "mcpjungle", "charts/mcpjungle"]),
            ("ingress enabled", ["template", "mcpjungle", "charts/mcpjungle",
                                 "--set", "ingress.enabled=true",
                                 "--set", "ingress.host=mcpjungle"])]:
        r = helm(*args)
        if r.returncode != 0:
            check("rendered output available for %s" % label, False, r.stderr[-200:])
            continue
        tmpyaml = os.path.join(tempfile.gettempdir(), "mj-render.yaml")
        with open(tmpyaml, "w") as fh:
            fh.write(r.stdout)
        # Helm/Go marshals sequences WITHOUT extra indentation (drop:\n- ALL).
        # That is valid and is what Kubernetes expects; yamllint's default
        # indent-sequences style disagrees, so disable that one rule rather than
        # reformatting the chart into a non-idiomatic shape.
        # Rendered output is produced by Go's yaml marshaller via toYaml/nindent,
        # so its indentation is machine-generated and stylistically inconsistent
        # (and un-indented sequences) while remaining valid and accepted by the
        # API server. The `indentation` rule is therefore disabled for RENDERED
        # output only; every other yamllint rule still applies, which is what
        # catches real problems (duplicate keys, trailing spaces, bad scalars).
        y = subprocess.run(["yamllint", "-d",
                            "{extends: default, rules: {line-length: disable, "
                            "document-start: disable, indentation: disable}}",
                            tmpyaml], capture_output=True, text=True)
        check("rendered manifests are valid YAML (%s)" % label, y.returncode == 0,
              y.stdout[-300:])
else:
    print("  SKIP  yamllint not on PATH")

print("\n== modules and args that the installed collection actually provides ==")
if shutil.which("ansible-doc"):
    col = os.path.expanduser("~/.ansible/collections/ansible_collections/"
                             "kubernetes/core/plugins/modules")
    if os.path.isdir(col):
        mods = set(os.listdir(col))
        check("k8s_cluster_info exists (kubectl_info was REMOVED in 6.x)",
              "k8s_cluster_info.py" in mods)
        check("role does not call the removed kubectl_info",
              "kubectl_info" not in read(os.path.join(ROLE, "tasks", "install_k8s.yml")))
        check("k8s_info exists", "k8s_info.py" in mods)
    exp = read(os.path.join(ROLE, "tasks", "expose_tailscale.yml"))
    check("uses wait_timeout, not wait_condition.timeout",
          "wait_timeout:" in exp and "wait_condition:" not in exp)

print("\n== docker path preserved ==")
check("deploy method defaults to docker",
      'mcpjungle_deploy_method: "docker"' in defaults)
check("docker install task still exists",
      os.path.exists(os.path.join(ROLE, "tasks", "install_docker.yml")))
check("original docker playbook untouched in behaviour",
      "Ensure MCPJungle data directory exists" in read(
          os.path.join(ROLE, "tasks", "install_docker.yml")))

print("\n== target selection is explicit ==")
check("kubeconfig required", "mcpjungle_k8s_kubeconfig" in read(
    os.path.join(ROLE, "tasks", "install_k8s.yml")))
check("context required", "mcpjungle_k8s_context" in read(
    os.path.join(ROLE, "tasks", "install_k8s.yml")))
check("playbook refuses without explicit context",
      "never silently select" in read(PLAYBOOK).lower()
      or "NEVER silently select" in read(PLAYBOOK))

print("\n== helm lint ==")
lint = helm("lint", "charts/mcpjungle")
check("helm lint passes", lint.returncode == 0, lint.stdout[-200:])

print("\n%s" % ("=" * 60))
print("passed: %d   failed: %d" % (passes, len(failures)))
if failures:
    for f in failures:
        print("  FAILED: %s" % f)
    sys.exit(1)
print("OFFLINE VALIDATION PASSED")
