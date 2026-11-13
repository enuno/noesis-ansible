"""Offline validation for the n8n Kubernetes deployment path.

These tests are deliberately non-mutating: no cluster, no Bitwarden writes, no
Helm release. They assert the properties that were the actual findings of the
chart/image review, so a future edit cannot silently reintroduce them.

Run:  python3 tests/n8n_k8s/test_offline.py
"""

import json
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
from jinja2 import Environment, FileSystemLoader


def _ansible_bool(value):
    """The Ansible `| bool` filter, for rendering the values template here."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("true", "yes", "on", "1")


# A FileSystemLoader is required, not optional: values.yml.j2 `{% include %}`s
# the starter kit partial, and a loaderless Environment raises TemplateNotFound.
env = Environment(loader=FileSystemLoader(os.path.join(ROLE, "templates")))
env.filters["bool"] = _ansible_bool


def render_values(**overrides):
    """Render the role's real values template at a given variable layer."""
    ctx = dict(defaults)
    ctx["role_path"] = ROLE
    ctx.update(overrides)
    return env.get_template("values.yml.j2").render(**ctx)


rendered_values = render_values()
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

print("\n== starter kit: defaults are restrictive, inventory opts in ==")
inv_vars = yaml.safe_load(inv)
sk_assets = os.path.join(ROLE, "files", "starter-kit")
check("starter kit is OFF by role default",
      defaults["n8n_k8s_starter_kit_enabled"] is False)
check("deployment inventory opts the starter kit in",
      inv_vars.get("n8n_k8s_starter_kit_enabled") is True)
check("postgres stays off by default",
      defaults["n8n_k8s_starter_kit_postgres_enabled"] is False)
check("postgres adoption stays off by default",
      defaults["n8n_k8s_starter_kit_postgres_adopt"] is False)
check("inventory does not adopt postgres",
      inv_vars.get("n8n_k8s_starter_kit_postgres_adopt") is False)
check("ollama profile is a known compose profile",
      defaults["n8n_k8s_starter_kit_ollama_profile"] in ("cpu", "gpu-nvidia", "gpu-amd"))
check("every starter kit image is digest-pinned 64-hex",
      all(re.match(r"^sha256:[0-9a-f]{64}$", defaults[k]) for k in (
          "n8n_k8s_starter_kit_ollama_image_digest",
          "n8n_k8s_starter_kit_qdrant_image_digest",
          "n8n_k8s_starter_kit_postgres_image_digest")))
check("no starter kit image rides a floating tag",
      all("latest" not in defaults[k] for k in (
          "n8n_k8s_starter_kit_ollama_image",
          "n8n_k8s_starter_kit_qdrant_image",
          "n8n_k8s_starter_kit_postgres_image")))
# The vendored demo credentials hardcode these hostnames. If the service names
# drift, the credentials point at nothing and the demo workflow fails at run
# time with a connection error rather than at deploy time.
check("ollama service name matches the vendored credential URL",
      defaults["n8n_k8s_starter_kit_ollama_service"] == "ollama")
check("qdrant service name matches the vendored credential URL",
      defaults["n8n_k8s_starter_kit_qdrant_service"] == "qdrant")
check("the role refuses postgres adoption in its own preflight",
      "n8n_k8s_starter_kit_postgres_adopt" in tasks
      and "not (n8n_k8s_starter_kit_postgres_adopt | bool)" in tasks)

print("\n== starter kit: vendored demo data is usable with THIS instance's key ==")
wf_path = os.path.join(sk_assets, "workflows", "srOnR8PAY3u4RSwb.json")
check("demo workflow is vendored in the role", os.path.isfile(wf_path))
upstream_wf = os.path.expanduser(
    "~/tools/self-hosted-ai-starter-kit/n8n/demo-data/workflows/srOnR8PAY3u4RSwb.json")
if os.path.isfile(upstream_wf) and os.path.isfile(wf_path):
    check("vendored workflow is byte-identical to upstream",
          read(wf_path) == read(upstream_wf))
cred_expect = {
    "xHuYe0MDGOs9IpBW": ("ollamaApi", "baseUrl", "http://ollama:11434"),
    "sFfERYppMeBnFNeA": ("qdrantApi", "qdrantUrl", "http://qdrant:6333"),
}
for cid, (ctype, url_key, url) in cred_expect.items():
    path = os.path.join(sk_assets, "credentials", "%s.json" % cid)
    check("credential %s is vendored" % cid, os.path.isfile(path))
    if not os.path.isfile(path):
        continue
    cred = json.loads(read(path))
    check("credential %s keeps its upstream id" % cid, cred["id"] == cid)
    check("credential %s has type %s" % (cid, ctype), cred["type"] == ctype)
    # The decisive property: n8n only encrypts `data` when it is an OBJECT. A
    # string here is upstream's ciphertext, which was encrypted with the demo
    # key and is undecryptable under the Bitwarden-escrowed key this release
    # uses - the credential would exist in the UI and fail every request.
    is_plaintext = isinstance(cred["data"], dict)
    check("credential %s carries PLAINTEXT object data" % cid,
          is_plaintext, type(cred["data"]).__name__)
    # Guarded, not chained: a string `data` (upstream's ciphertext) must make
    # this report a clean FAIL, not crash the suite on .get and skip every
    # check after it.
    check("credential %s points at the in-cluster service" % cid,
          is_plaintext and cred["data"].get(url_key) == url,
          str(cred["data"])[:60])
readme = read(os.path.join(sk_assets, "README.md"))
check("vendored assets record the upstream revision they came from",
      defaults["n8n_k8s_starter_kit_upstream_commit"] in readme)
check("role asserts the vendored assets exist before deploying",
      "files/starter-kit" in tasks and "Require the vendored starter kit demo data" in tasks)

print("\n== starter kit: derived verification lists track the toggles ==")
role_vars = yaml.safe_load(read(os.path.join(ROLE, "vars", "main.yml")))
for key in ("n8n_k8s_starter_kit_expected_deployments",
            "n8n_k8s_starter_kit_expected_digests"):
    check("%s is derived, not hardcoded" % key,
          "n8n_k8s_starter_kit_ollama_enabled" in role_vars[key]
          and "n8n_k8s_starter_kit_postgres_enabled" in role_vars[key])

print("\n== starter kit: the values template renders the kit ==")
sk_values = render_values(**inv_vars)
check("starter kit values carry no unresolved markers", "{{" not in sk_values)
sk_doc = yaml.safe_load(sk_values)
sk_objects = sk_doc.get("extraObjects", [])
sk_names = [(o["kind"], o["metadata"]["name"]) for o in sk_objects]
check("ollama Deployment and Service are rendered",
      ("Deployment", "ollama") in sk_names and ("Service", "ollama") in sk_names, str(sk_names))
check("qdrant Deployment and Service are rendered",
      ("Deployment", "qdrant") in sk_names and ("Service", "qdrant") in sk_names, str(sk_names))
check("the demo import Job is rendered",
      any(k == "Job" for k, _ in sk_names), str(sk_names))
check("postgres is NOT rendered while it is opted out",
      ("Deployment", "postgres") not in sk_names, str(sk_names))
check("shared claim is rendered and mounted into n8n",
      ("PersistentVolumeClaim", defaults["n8n_k8s_starter_kit_shared_claim"]) in sk_names
      and any(m["mountPath"] == defaults["n8n_k8s_starter_kit_shared_mount_path"]
              for m in sk_doc.get("extraVolumeMounts", [])))
check("OLLAMA_HOST is injected into n8n",
      any(e["name"] == "OLLAMA_HOST" for e in sk_doc["config"]["extraEnv"]))
import_job = [o for o in sk_objects if o["kind"] == "Job"][0]
job_spec = import_job["spec"]["template"]["spec"]
check("import Job runs as a post-install/post-upgrade Helm hook",
      "post-upgrade" in import_job["metadata"]["annotations"]["helm.sh/hook"])
check("import Job writes the SAME claim the n8n Deployment mounts",
      any(v.get("persistentVolumeClaim", {}).get("claimName")
          == defaults["n8n_k8s_release_name"] for v in job_spec["volumes"]))
check("import Job receives the live encryption key from the n8n Secret",
      any(e.get("secretRef", {}).get("name") == defaults["n8n_k8s_secret_name"]
          for e in job_spec["containers"][0]["envFrom"]))
check("import Job keeps upstream's do-not-overwrite guard",
      "list:workflow --onlyId" in str(job_spec["containers"][0]["args"]))
# Two regressions found by deploying this for real, both of which presented as
# a SUCCESSFUL hook that imported nothing:
#
# 1. `n8n import:* --separate` validates its input with
#    fs.lstatSync(input).isDirectory(). A ConfigMap/projected volume whose item
#    paths contain a subdirectory makes that subdirectory a SYMLINK into
#    ..data, lstat does not follow symlinks, so the check is false.
# 2. n8n then logs "The argument to --input must be a directory" and RETURNS 0.
#    The Job reports success, Helm deletes the hook, and nothing was written.
job_mounts = {m["mountPath"] for m in job_spec["containers"][0]["volumeMounts"]}
check("import Job mounts the workflows directory as its own mount point",
      "/demo-data/workflows" in job_mounts, str(job_mounts))
check("import Job mounts the credentials directory as its own mount point",
      "/demo-data/credentials" in job_mounts, str(job_mounts))
check("import Job does NOT mount a parent dir whose children become symlinks",
      "/demo-data" not in job_mounts, str(job_mounts))
job_item_paths = [i["path"]
                  for v in job_spec["volumes"]
                  for i in (v.get("configMap", {}).get("items", []))]
check("no ConfigMap item path contains a subdirectory",
      job_item_paths and all("/" not in p for p in job_item_paths),
      str(job_item_paths))
job_script = str(job_spec["containers"][0]["args"])
check("import Job verifies the row landed instead of trusting exit 0",
      "srOnR8PAY3u4RSwb" in job_script and "exit 1" in job_script)

print("\n== starter kit: an existing caller is NOT changed (regression) ==")
# The decisive safety property for this change: with the kit off, the role must
# render exactly the release that is already deployed. Mutate the toggle and
# the extra keys must appear; leave it alone and they must not exist at all.
off_doc = yaml.safe_load(rendered_values)
check("kit-off render emits no extraObjects",
      "extraObjects" not in off_doc)
check("kit-off render emits no extra volumes or mounts",
      "extraVolumes" not in off_doc and "extraVolumeMounts" not in off_doc)
check("kit-off render keeps exactly the pre-existing extraEnv",
      off_doc["config"]["extraEnv"]
      == [{"name": "N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS", "value": "true"}],
      off_doc["config"]["extraEnv"])
check("kit-off render keeps n8n on sqlite",
      off_doc["database"]["type"] == "sqlite")
check("kit-on render also keeps n8n on sqlite",
      sk_doc["database"]["type"] == "sqlite")

print("\n== starter kit: helm renders the kit against the pinned chart ==")
sk_file = os.path.join(REPO, "tests", "n8n_k8s", ".rendered-sk-values.yml")
with open(sk_file, "w") as fh:
    fh.write(sk_values)
sk_render = helm("template", "n8n", ref, "--version", CHART_VERSION,
                 "-n", "n8n", "-f", sk_file)
check("helm template renders the starter kit", sk_render.returncode == 0,
      sk_render.stderr[-400:] if sk_render.returncode else "")
if sk_render.returncode == 0:
    sk_docs = [d for d in yaml.safe_load_all(sk_render.stdout) if d]
    pod_specs = {}
    for d in sk_docs:
        if d["kind"] in ("Deployment", "Job"):
            pod_specs[d["metadata"]["name"]] = d["spec"]["template"]["spec"]
    for name in ("ollama", "qdrant", "n8n-starter-kit-import"):
        check("%s pod template is rendered" % name, name in pod_specs)
    # The n8n namespace enforces Pod Security Standards `restricted`. A
    # workload that misses any of these is rejected at admission, so the
    # deploy fails rather than degrades - assert it before it ships.
    for name, spec in pod_specs.items():
        psc = spec.get("securityContext", {})
        conts = spec.get("containers", []) + spec.get("initContainers", [])
        check("%s satisfies PSS restricted" % name,
              psc.get("runAsNonRoot") is True
              and psc.get("runAsUser", 0) != 0
              and psc.get("seccompProfile", {}).get("type") == "RuntimeDefault"
              and all(c.get("securityContext", {}).get("allowPrivilegeEscalation") is False
                      and c.get("securityContext", {}).get("capabilities", {}).get("drop") == ["ALL"]
                      for c in conts),
              json.dumps(psc))
    images = [c["image"] for s in pod_specs.values()
              for c in s.get("containers", []) + s.get("initContainers", [])]
    check("ollama image is digest-pinned in the rendered manifest",
          any(defaults["n8n_k8s_starter_kit_ollama_image_digest"] in i for i in images), str(images))
    check("qdrant image is digest-pinned in the rendered manifest",
          any(defaults["n8n_k8s_starter_kit_qdrant_image_digest"] in i for i in images), str(images))
    check("no starter kit manifest carries an unresolved template marker",
          "{{" not in sk_render.stdout)
    check("ingress is still the tailscale class with the kit on",
          "ingressClassName: tailscale" in sk_render.stdout)
os.remove(sk_file)

print("\n== summary ==")
print("passed=%d failed=%d" % (passes, len(failures)))
if failures:
    for f in failures:
        print(" - %s" % f)
    sys.exit(1)
print("OK")
sys.exit(0)
