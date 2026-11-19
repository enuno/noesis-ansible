"""Offline validation for the GBrain Kubernetes deployment path.

Run: python3 tests/gbrain_k8s/test_offline.py
"""
import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CHART = os.path.join(REPO, "charts", "gbrain")
ROLE = os.path.join(REPO, "roles", "gbrain_k8s")
PLAYBOOK = os.path.join(REPO, "playbooks", "gbrain-k8s.yml")
INV = os.path.join(REPO, "inventory", "gbrain-k8s", "group_vars", "all.yml")
REQUIRED_PROJECT = "72974d0e-81af-4678-bab7-b46000985859"

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


print("== chart provenance ==")
chart_yaml = read(os.path.join(CHART, "Chart.yaml"))
check("appVersion pinned", 'appVersion: "0.60.747.0"' in chart_yaml)
check("kubeVersion present", "kubeVersion" in chart_yaml)
check("no official upstream chart recorded", "upstream-chart: none" in chart_yaml)

print("\n== helm lint ==")
lint = helm("lint", "charts/gbrain")
check("helm lint", lint.returncode == 0, lint.stdout + lint.stderr)

print("\n== helm template (ingress off) ==")
off = helm("template", "gbrain", "charts/gbrain")
check("template ingress-off", off.returncode == 0, off.stderr[:400])
out = off.stdout
check("no LoadBalancer", "type: LoadBalancer" not in out)
check("ClusterIP service", "type: ClusterIP" in out)
check("bind 0.0.0.0", "--bind" in out and "0.0.0.0" in out)
check("port 3131", "3131" in out)
check("serve --http", "--http" in out)
check("GBRAIN_DATABASE_URL from secret", "name: GBRAIN_DATABASE_URL" in out and "secretKeyRef" in out)
check("GBRAIN_DIRECT_DATABASE_URL from secret", "name: GBRAIN_DIRECT_DATABASE_URL" in out)
check("no Ingress when disabled", "kind: Ingress" not in out)
check("image not latest", ":latest" not in out)

print("\n== helm template (ingress on) ==")
on = helm(
    "template",
    "gbrain",
    "charts/gbrain",
    "--set",
    "ingress.enabled=true",
    "--set",
    "ingress.host=gbrain",
)
check("template ingress-on", on.returncode == 0, on.stderr[:400])
ing = on.stdout
check("Ingress class tailscale", "ingressClassName: tailscale" in ing)
check("short host gbrain", 'host: "gbrain"' in ing)
check("tls includes host", '- "gbrain"' in ing)
check("Prefix / backend", "path: /" in ing)
check("no proxy-group annotation", "proxy-group" not in ing)

print("\n== role prefix and inventory ==")
defaults = read(os.path.join(ROLE, "defaults", "main.yml"))
inv = read(INV)
install = read(os.path.join(ROLE, "tasks", "install.yml"))
check("role prefix gbrain_k8s_", "gbrain_k8s_kubeconfig" in defaults)
check("inventory uses same prefix", "gbrain_k8s_kubeconfig" in inv)
check("BW project pinned", REQUIRED_PROJECT in defaults and REQUIRED_PROJECT in inv)
check("chart_ref uses role_path", "role_path" in install and "charts/gbrain" in install)
check("expose default off", "gbrain_k8s_expose_enabled: false" in defaults)
check("no master-stack include", "master-stack" not in read(PLAYBOOK))
check("reserved hostnames listed", "tailscale-operator" in defaults)

print("\n== Dockerfile ==")
df = read(os.path.join(CHART, "docker", "Dockerfile"))
check("Dockerfile bind 0.0.0.0", '"--bind", "0.0.0.0"' in df)
check("Dockerfile not pglite init", "pglite" not in df.lower())
check("Chart.yaml pin is a real field", re.search(r'^appVersion: "0.60.747.0"', chart_yaml, re.M) is not None)

print("\n== yamllint rendered (ingress on) ==")
with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
    fh.write(ing)
    rendered_path = fh.name
yl = subprocess.run(
    [
        "yamllint",
        "-d",
        "{extends: default, rules: {indentation: disable, line-length: disable}}",
        rendered_path,
    ],
    capture_output=True,
    text=True,
)
check("yamllint rendered ingress-on", yl.returncode == 0, yl.stdout[:300] + yl.stderr[:200])

with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
    fh.write("a: 1\na: 2\n")
    bad = fh.name
yl_bad = subprocess.run(["yamllint", bad], capture_output=True, text=True)
check("yamllint catches duplicate key", yl_bad.returncode != 0)

if __name__ == "__main__":
    print("\npassed: %s  failed: %s" % (passes, len(failures)))
    if failures:
        for item in failures:
            print("FAIL", item)
        sys.exit(1)
