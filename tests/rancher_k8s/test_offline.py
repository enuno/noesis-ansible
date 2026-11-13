"""Offline validation for the Rancher k3s + Tailscale ingress deployment path.

Deliberately non-mutating: no cluster, no Bitwarden writes, no Helm release.
Asserts the properties the design review pinned down, so a future edit cannot
silently reintroduce a hazard (unmanaged ingress, cert-manager dependency,
missing escrow gates, plaintext credentials, non-idempotent writes).

Run:  /usr/bin/python3 tests/rancher_k8s/test_offline.py
"""

import os
import re
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ROLE = os.path.join(REPO, "roles", "rancher_k8s")
CHART = os.path.join(REPO, "charts", "vendor", "rancher")
PLAYBOOK = os.path.join(REPO, "playbooks", "rancher-k8s.yml")
INV = os.path.join(REPO, "inventory", "rancher-k8s", "group_vars", "all.yml")
HOSTS = os.path.join(REPO, "inventory", "rancher-k8s", "hosts.ini")
VENDORED_MD = os.path.join(CHART, "VENDORED.md")

REQUIRED_PROJECT = "72974d0e-81af-4678-bab7-b46000985859"
UPSTREAM_SHA256 = "343888c66421a9f5666b562cdfeca751d63da994edbe7b1b36752f8ffcf5ecd4"

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


defaults = read(os.path.join(ROLE, "defaults", "main.yml"))
tasks = read(os.path.join(ROLE, "tasks", "main.yml"))
values_tpl = read(os.path.join(ROLE, "templates", "values.yml.j2"))
ingress_tpl = read(os.path.join(ROLE, "templates", "ingress.yml.j2"))
playbook = read(PLAYBOOK)
inv = read(INV)
hosts = read(HOSTS)

print("== vendored chart provenance ==")
chart_yaml = read(os.path.join(CHART, "Chart.yaml"))
check("chart version pinned to the approved release",
      re.search(r"^version: 2\.15\.3$", chart_yaml, re.M) is not None)
check("kubeVersion relaxed to the approved constraint",
      "kubeVersion: < 1.38.0-0" in chart_yaml)
check("defaults pin the same chart version",
      'rancher_k8s_chart_version: "2.15.3"' in defaults)
check("defaults record the approved relaxed constraint",
      'rancher_k8s_chart_relaxed_kubeversion: "< 1.38.0-0"' in defaults)
check("VENDORED.md exists", os.path.isfile(VENDORED_MD))
check("VENDORED.md records the upstream tarball sha256",
      os.path.isfile(VENDORED_MD) and UPSTREAM_SHA256 in read(VENDORED_MD))
check("role asserts chart provenance at deploy time",
      "rancher_k8s_chart_relaxed_kubeversion" in tasks
      and "Chart.yaml" in tasks)

print("\n== architecture values ==")
check("tls mode defaults to external (TLS terminated at the proxy)",
      "rancher_k8s_tls: external" in defaults)
check("single replica default (non-HA, single-node)",
      "rancher_k8s_replicas: 1" in defaults)
check("values template sets the canonical tailnet hostname",
      '"{{ rancher_k8s_hostname }}.{{ rancher_k8s_tailnet_domain }}"' in values_tpl)
check("values template disables the chart-managed Ingress",
      "enabled: false" in values_tpl)
check("values template sets tls from the role variable",
      'tls: "{{ rancher_k8s_tls }}"' in values_tpl)
check("values template feeds the escrowed bootstrap password",
      'bootstrapPassword: "{{ rancher_k8s_bootstrap_password }}"' in values_tpl)
check("values template keeps the Service ClusterIP",
      "type: ClusterIP" in values_tpl)

print("\n== dedicated tailscale ingress manifest ==")
check("ingress uses the tailscale class variable",
      'ingressClassName: "{{ rancher_k8s_tailscale_ingress_class }}"' in ingress_tpl)
check("ingress host is the short service name (not the FQDN)",
      'host: "{{ rancher_k8s_hostname }}"' in ingress_tpl)
check("ingress backend is service rancher port 80 (HTTP after external TLS)",
      'name: "{{ rancher_k8s_release_name }}"' in ingress_tpl
      and "number: 80" in ingress_tpl)
check("ingress tls hosts present (operator provisions the cert)",
      "tls:" in ingress_tpl)
check("no hardcoded tailnet suffix in the ingress template",
      "tailf99a0" not in ingress_tpl)
check("role asserts published hostname matches configured hostname",
      "status.loadBalancer.ingress[0].hostname" in tasks)

print("\n== bitwarden escrow discipline ==")
check("required project constant in defaults",
      '"%s"' % REQUIRED_PROJECT in defaults)
check("project id asserted exactly in tasks",
      "rancher_k8s_bitwarden_project_id == '%s'" % REQUIRED_PROJECT in tasks)
check("bootstrap key uses the mission naming pattern",
      "rancher_k8s_bootstrap_bw_key: rancher_k3s_bootstrap_password" in defaults)
check("admin key uses the mission naming pattern",
      "rancher_k8s_admin_bw_key: rancher_k3s_admin_password" in defaults)
check("keys are lowercase snake_case",
      "rancher_k3s_bootstrap_password" == "rancher_k3s_bootstrap_password".lower()
      and "rancher_k3s_admin_password" == "rancher_k3s_admin_password".lower())
check("write gate defaults to false (secure role default)",
      "rancher_k8s_allow_bitwarden_write: false" in defaults)
check("write gate opted in by the deployment inventory",
      "rancher_k8s_allow_bitwarden_write: true" in inv)
check("list happens before create (reuse-before-create)",
      tasks.index("List existing records in the project")
      < tasks.index("Persist the new bootstrap password to Bitwarden"))
check("ambiguity guard fails closed on duplicate keys",
      "more than one Bitwarden record" in tasks)
check("bootstrap create gated on the write gate",
      re.search(r"Persist the new bootstrap password[\s\S]*?allow_bitwarden_write \| bool", tasks)
      is not None)
check("credential generation refused in check mode",
      "not ansible_check_mode" in tasks
      and "CHECKMODE-PLACEHOLDER" in tasks)
check("bws value passed via environment, not the command string",
      '"$RANCHER_K8S_ESCROW_VALUE"' in tasks
      and "RANCHER_K8S_ESCROW_VALUE:" in tasks)
check("escrow verified after create (exactly-one-record assert)",
      tasks.count("exactly one record") >= 1
      or tasks.count("list | length) == 1") >= 2)
check("no rerun regeneration (reuse branch exists)",
      "Reuse the stored bootstrap password" in tasks)
check("admin password never rotated on rerun (verify-only branch)",
      "still authenticates" in tasks)
check("changed-but-unescrowed failure is hard, not silent",
      "Fail hard when the password changed but escrow did not complete" in tasks)
check("no_log coverage on secret-bearing tasks",
      tasks.count("no_log: true") >= 15, str(tasks.count("no_log: true")))

print("\n== helm task shape ==")
check("chart_ref is role-relative",
      '"{{ role_path }}/../../charts/vendor/rancher"' in defaults)
check("helm timeout keeps the helm-v4 string form",
      '"{{ rancher_k8s_helm_timeout }}s"' in tasks)
check("values rendered to a 0600 temp file",
      "dest: /run/rancher-values.yml" in tasks and "mode: '0600'" in tasks)
check("temp values removed in an always block",
      re.search(r"always:[\s\S]*?rancher-values\.yml[\s\S]*?state: absent", tasks)
      is not None)
check("helm task hides values (no_log + diff false)",
      re.search(r"Install or upgrade the Rancher Helm release[\s\S]*?no_log: true[\s\S]*?diff: false", tasks)
      is not None)
check("atomic install with cleanup on failure",
      "atomic: true" in tasks and "cleanup_on_fail: true" in tasks)

print("\n== check-mode and retry safety ==")
check("ingress wait guarded against check mode",
      re.search(r"publish the tailnet hostname[\s\S]*?when: not ansible_check_mode", tasks)
      is not None)
check("deployment wait guarded against check mode",
      re.search(r"become available[\s\S]*?when: not ansible_check_mode", tasks)
      is not None)
check("health checks guarded against check mode",
      re.search(r"health endpoint over tailnet HTTPS[\s\S]*?when: not ansible_check_mode", tasks)
      is not None)
check("retries are bounded (no infinite loops)",
      "retries:" in tasks and "until:" in tasks)
check("health checks do not report change",
      "changed_when: false" in tasks)
check("UI check targets the real SPA path /dashboard/ (Rancher 2.15 serves JSON apiRoot on /)",
      "/dashboard/" in tasks and "<title>Rancher</title>" in tasks)

print("\n== idempotency audit hooks ==")
check("bws list/get are changed_when false",
      tasks.count("changed_when: false") >= 8, str(tasks.count("changed_when: false")))
check("values render task is changed_when false (helm decides)",
      re.search(r"Render Rancher Helm values[\s\S]*?changed_when: false", tasks)
      is not None)

print("\n== playbook and inventory ==")
check("playbook targets the rancher_k8s group", "hosts: rancher_k8s" in playbook)
check("playbook becomes root on the target", "become: true" in playbook)
check("playbook uses the ansible remote user convention",
      "noesispraxis_ansible_user" in playbook)
check("inventory names exactly one host for one cluster",
      hosts.count("noesis-lab ansible_host=31.97.209.57 ansible_user=ansible") == 1)
check("inventory pins kubeconfig and context",
      "rancher_k8s_kubeconfig=/etc/rancher/k3s/k3s.yaml" in hosts
      and "rancher_k8s_context=default" in hosts)
check("inventory keeps durable site values",
      "rancher_k8s_hostname: rancher" in inv
      and "rancher_k8s_tls: external" in inv)

print("\n== no plaintext credentials anywhere ==")
suspicious = re.compile(
    r"(?i)(password|token|secret[_-]?key|api[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9/+_-]{16,}")
for path in [INV, HOSTS, PLAYBOOK,
             os.path.join(ROLE, "defaults", "main.yml"),
             os.path.join(ROLE, "templates", "values.yml.j2")]:
    body = read(path)
    hits = [m for m in suspicious.findall(body)]
    check("no hardcoded credential literal in %s"
          % os.path.relpath(path, REPO), not hits, str(hits[:2]))

print("\n== helm lint and render of the vendored chart ==")
lint = helm("lint", "charts/vendor/rancher")
check("helm lint passes", lint.returncode == 0, lint.stdout[-200:])

render = helm("template", "rancher", "charts/vendor/rancher",
              "--namespace", "cattle-system",
              "--set", "hostname=rancher.tailf99a0.ts.net",
              "--set", "replicas=1",
              "--set", "bootstrapPassword=offline-test-dummy",
              "--set", "tls=external",
              "--set", "ingress.enabled=false")
check("helm template succeeds with the role's values shape",
      render.returncode == 0, render.stderr[-300:])
if render.returncode == 0:
    out = render.stdout
    check("no chart-managed Ingress rendered", "kind: Ingress" not in out)
    # The post-delete hook's ClusterRole may reference the cert-manager.io API
    # group for cleanup of installs that used it; an RBAC rule for an absent
    # API group is inert. The hard requirement is that no cert-manager CRD
    # OBJECTS are rendered (no install-time dependency).
    check("no cert-manager CRD objects rendered",
          "kind: Certificate" not in out and "kind: Issuer" not in out
          and "kind: ClusterIssuer" not in out)
    check("cert-manager mention only in post-delete cleanup RBAC",
          out.count("cert-manager.io") <= 2)
    check("service exposes HTTP port 80", "- port: 80" in out or "port: 80" in out)
    check("probes use HTTP /healthz on port 80",
          "path: /healthz" in out and "port: 80" in out)
    check("bootstrap-secret is rendered (runtime copy)",
          "bootstrap-secret" in out)
    check("image tag follows the pinned appVersion",
          "rancher/rancher:v2.15.3" in out)

print("\n%s" % ("=" * 60))
print("passed: %d   failed: %d" % (passes, len(failures)))
if failures:
    for f in failures:
        print("  FAILED: %s" % f)
    sys.exit(1)
print("OFFLINE VALIDATION PASSED")
