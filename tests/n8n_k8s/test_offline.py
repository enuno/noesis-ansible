"""Offline validation for the n8n Kubernetes deployment path.

These tests are deliberately non-mutating: no cluster, no Bitwarden writes, no
Helm release. They assert the properties that were the actual findings of the
chart/image review, so a future edit cannot silently reintroduce them.

Run:  python3 tests/n8n_k8s/test_offline.py
"""

import os
import re
import subprocess
import sys

import yaml

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ROLE = os.path.join(REPO, "roles", "n8n_k8s")
DEFAULTS = os.path.join(ROLE, "defaults", "main.yml")
TASKS = os.path.join(ROLE, "tasks", "main.yml")
VALUES_TPL = os.path.join(ROLE, "templates", "values.yml.j2")
PLAYBOOK = os.path.join(REPO, "playbooks", "n8n-k8s.yml")
INV = os.path.join(REPO, "inventory", "n8n-k8s", "group_vars", "all.yml")

CHART_REF = "oci://ghcr.io/n8n-io/n8n-helm-chart/n8n"
CHART_VERSION = "1.19.0"
CHART_APP_VERSION = "2.47.4"
APP_VERSION = "2.47.5"
CHART_DIGEST = (
    "sha256:13b8065b5e3dc657800c300fee36e976f692bb1382930c2ff317944814762943"
)
IMAGE_DIGEST = (
    "sha256:e29e9cc965a16d07d989f115f729f8a1c7aff58688d4850247fa495d4d7aae2f"
)
RUNNER_DIGEST = (
    "sha256:1f53745aaaf08758f86c4653545799b6b77fcae354e037af65b34290c93fe28e"
)

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


def read(path):
    with open(path) as fh:
        return fh.read()


def helm(*args):
    return subprocess.run(["helm", *args], capture_output=True, text=True, cwd=REPO)


defaults = yaml.safe_load(read(DEFAULTS))
tasks = read(TASKS)
values_tpl = read(VALUES_TPL)
playbook = read(PLAYBOOK)
inv = read(INV)

print("== version pins are coherent ==")
check("chart version pinned", defaults["n8n_k8s_chart_version"] == CHART_VERSION,
      defaults.get("n8n_k8s_chart_version"))
check("chart digest pinned", defaults["n8n_k8s_chart_digest"] == CHART_DIGEST,
      defaults.get("n8n_k8s_chart_digest"))
check("chart appVersion pinned",
      defaults["n8n_k8s_chart_app_version"] == CHART_APP_VERSION,
      defaults.get("n8n_k8s_chart_app_version"))
check("app version pinned", defaults["n8n_k8s_app_version"] == APP_VERSION,
      defaults.get("n8n_k8s_app_version"))
check("image tag equals app version",
      defaults["n8n_k8s_image_tag"] == defaults["n8n_k8s_app_version"],
      defaults.get("n8n_k8s_image_tag"))
check("image digest pinned",
      defaults["n8n_k8s_image_digest"] == IMAGE_DIGEST,
      defaults.get("n8n_k8s_image_digest"))
check("runner image digest pinned",
      defaults["n8n_k8s_runner_image_digest"] == RUNNER_DIGEST,
      defaults.get("n8n_k8s_runner_image_digest"))
check("chart ref is the official n8n OCI chart",
      defaults["n8n_k8s_chart_ref"] == CHART_REF,
      defaults.get("n8n_k8s_chart_ref"))
check("app version is on the chart's minor line",
      APP_VERSION.split(".")[:2] == CHART_APP_VERSION.split(".")[:2],
      "%s vs %s" % (APP_VERSION, CHART_APP_VERSION))
check("digests are 64-hex sha256",
      all(re.match(r"^sha256:[0-9a-f]{64}$", d) for d in (
          defaults["n8n_k8s_chart_digest"],
          defaults["n8n_k8s_image_digest"],
          defaults["n8n_k8s_runner_image_digest"])))
check("no floating latest tag",
      "latest" not in defaults["n8n_k8s_image_tag"])

print("\n== the digest pin is enforced, not decorative ==")
# Scope the check to the kubernetes.core.helm task itself. The digest also
# appears in the preflight task, so a whole-file substring check would keep
# passing even if the apply-time pin were removed.
helm_task = ""
for block in re.split(r"(?m)^- name: ", tasks):
    if "kubernetes.core.helm:" in block:
        helm_task = block
        break
check("helm task was found", bool(helm_task))
check("chart_ref is digest-pinned at apply time",
      '"{{ n8n_k8s_chart_ref }}@{{ n8n_k8s_chart_digest }}"' in helm_task)
check("chart_version is still passed alongside the digest",
      'chart_version: "{{ n8n_k8s_chart_version }}"' in helm_task)
check("preflight resolves chart metadata from the registry",
      "helm" in tasks and "show" in tasks and "chart" in tasks)
check("preflight asserts the resolved chart version",
      "n8n_k8s_chart_metadata" in tasks
      and "n8n_k8s_chart_version" in tasks)
check("preflight asserts the resolved chart appVersion",
      "n8n_k8s_chart_app_version" in tasks)
check("preflight asserts the digest resolves to the pinned version",
      "n8n_k8s_chart_digest_check" in tasks)
check("helm binary path is pinned and asserted",
      "n8n_k8s_helm_binary_path" in defaults and "n8n_k8s_helm_binary_path" in tasks)

print("\n== the deployed image is verified, not assumed ==")
check("post-deploy check reads the running pods",
      "kind: Pod" in tasks and "label_selectors" in tasks)
check("post-deploy check asserts the n8n image digest",
      "n8n_k8s_image_digest" in tasks and "imageID" in tasks)
check("post-deploy check asserts the runner image digest",
      "n8n_k8s_runner_image_digest" in tasks)
check("pod image list is flattened before matching imageID",
      "flatten" in tasks)

print("\n== secret handling ==")
check("encryption key is read from Bitwarden",
      "N8N_K3S_DEFAULT_ENCRYPTION_KEY" in defaults
      or "n8n_k8s_encryption_bw_key" in defaults)
check("runner token is read from Bitwarden",
      "n8n_k8s_runner_bw_key" in defaults)
check("secret values are never logged",
      "no_log: true" in tasks)
check("encryption key is not hardcoded in the repo",
      "N8N_ENCRYPTION_KEY:" not in values_tpl)

print("\n== values template ==")
check("image tag comes from the pinned variable",
      "n8n_k8s_image_tag" in values_tpl)
check("image repository comes from the pinned variable",
      "n8n_k8s_image_repository" in values_tpl)
check("task runner tag is not set separately, so it tracks image.tag",
      "taskRunners:" in values_tpl and "tag:" not in
      values_tpl.split("taskRunners:")[1].split("replicaCount")[0])
check("secret is referenced by name, not inlined",
      "existingSecret" in values_tpl and "N8N_ENCRYPTION_KEY" not in values_tpl)

print("\n== helm render against the pinned chart ==")
# Render the role's real values template so the render exercises what the
# role actually applies, instead of a hand-written approximation.
from jinja2 import Environment


def _ansible_bool(value):
    """The Ansible `| bool` filter, for rendering the values template here."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("true", "yes", "on", "1")


env = Environment()
env.filters["bool"] = _ansible_bool
rendered_values = env.from_string(values_tpl).render(**defaults)
check("values template renders with the role defaults",
      "{{" not in rendered_values, rendered_values[:200])
values_file = os.path.join(REPO, "tests", "n8n_k8s", ".rendered-values.yml")
with open(values_file, "w") as fh:
    fh.write(rendered_values)

ref = "%s@%s" % (CHART_REF, CHART_DIGEST)
render = helm("template", "n8n", ref, "--version", CHART_VERSION,
              "-n", "n8n", "-f", values_file)
check("helm template renders", render.returncode == 0,
      render.stderr[-300:] if render.returncode else "")
if render.returncode == 0:
    out = render.stdout
    check("n8n image renders the pinned app version",
          "docker.n8n.io/n8nio/n8n:%s" % APP_VERSION in out)
    check("task runner image tracks the app version",
          "n8nio/runners:%s" % APP_VERSION in out)
    check("no placeholder encryption key is rendered",
          "change-me-to-a-long-random-key" not in out)
    check("ingress class is tailscale", "ingressClassName: tailscale" in out)
    check("chart version is stamped on rendered objects",
          "helm.sh/chart: n8n-%s" % CHART_VERSION in out)
    check("rendered values carry no unresolved template markers",
          "{{" not in out)
os.remove(values_file)

print("\n== deployment target is explicit ==")
check("playbook targets the n8n group", "hosts: n8n_k8s" in playbook)
check("playbook is standalone, not wired into master-stack",
      "n8n_k8s" not in read(os.path.join(REPO, "playbooks", "master-stack.yml")))
check("kubeconfig and context are required",
      "n8n_k8s_kubeconfig" in playbook and "n8n_k8s_context" in playbook)
check("inventory keeps the n8n hostname",
      "n8n_k8s_hostname: n8n" in inv)

print("\n== summary ==")
print("passed=%d failed=%d" % (passes, len(failures)))
if failures:
    for f in failures:
        print(" - %s" % f)
    sys.exit(1)
print("OK")
sys.exit(0)
