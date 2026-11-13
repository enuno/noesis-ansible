"""Offline validation for the Radar k3s + Tailscale ingress deployment path.

Non-mutating: no cluster contact. Run:
  /usr/bin/python3 tests/radar_k8s/test_offline.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ROLE = os.path.join(REPO, "roles", "radar_k8s")
CHART = os.path.join(REPO, "charts", "vendor", "radar")
PLAYBOOK = os.path.join(REPO, "playbooks", "radar-k8s.yml")
INV = os.path.join(REPO, "inventory", "radar-k8s", "group_vars", "all.yml")
HOSTS = os.path.join(REPO, "inventory", "radar-k8s", "hosts.ini")
VENDORED_MD = os.path.join(CHART, "VENDORED.md")
CHART_SHA = "5a76a6b7c60cc7c5cee625ea667b8f7ad0272920bdf0ce19d6fe201a9bb18087"
IMAGE_DIGEST = "sha256:68fe38aeb010a0a4b5110667a03a97b2e03f045559acdc31721a1f6c529f6cb7"

failures: list[str] = []
passes = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passes
    if cond:
        passes += 1
        print("  PASS  %s" % name)
    else:
        failures.append("%s %s" % (name, detail))
        print("  FAIL  %s %s" % (name, detail))


def read(path: str) -> str:
    with open(path) as fh:
        return fh.read()


def helm(*args: str) -> subprocess.CompletedProcess:
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
check("chart version pinned to 1.20.2",
      re.search(r"^version: 1\.20\.2$", chart_yaml, re.M) is not None)
check("appVersion pinned to 1.20.2",
      re.search(r"^appVersion: 1\.20\.2$", chart_yaml, re.M) is not None
      or 'appVersion: "1.20.2"' in chart_yaml
      or "appVersion: 1.20.2" in chart_yaml)
check("defaults pin chart version 1.20.2",
      'radar_k8s_chart_version: "1.20.2"' in defaults)
check("defaults pin image tag 1.20.2",
      'radar_k8s_image_tag: "1.20.2"' in defaults)
check("VENDORED.md exists", os.path.isfile(VENDORED_MD))
check("VENDORED.md records package sha256",
      os.path.isfile(VENDORED_MD) and CHART_SHA in read(VENDORED_MD))
check("VENDORED.md records image digest",
      os.path.isfile(VENDORED_MD) and IMAGE_DIGEST in read(VENDORED_MD))
check("role asserts Chart.yaml version at deploy time",
      "radar_k8s_chart_version" in tasks and "Chart.yaml" in tasks)
check("inventory pins image digest", IMAGE_DIGEST in inv)

print("\n== architecture values ==")
check("auth mode defaults to none (tailnet trust boundary)",
      "radar_k8s_auth_mode: none" in defaults)
check("values template disables chart-managed Ingress",
      "enabled: false" in values_tpl)
check("values template keeps Service ClusterIP",
      "type: ClusterIP" in values_tpl)
check("values template sets service port from role var",
      "port: {{ radar_k8s_service_port | int }}" in values_tpl)
check("values template sets auth mode from role var",
      'mode: "{{ radar_k8s_auth_mode }}"' in values_tpl)
check("values template keeps rbac.helm off by default path",
      "helm: {{ radar_k8s_rbac_helm | bool | lower }}" in values_tpl)
check("defaults keep rbac.helm false",
      "radar_k8s_rbac_helm: false" in defaults)
check("values template sets allowedHosts for MagicDNS FQDN",
      "allowedHosts:" in values_tpl
      and 'radar_k8s_hostname }}.{{ radar_k8s_tailnet_domain' in values_tpl)

print("\n== dedicated tailscale ingress ==")
check("ingress uses tailscale class variable",
      'ingressClassName: "{{ radar_k8s_tailscale_ingress_class }}"' in ingress_tpl)
check("ingress host is short service name",
      'host: "{{ radar_k8s_hostname }}"' in ingress_tpl)
check("ingress backend is radar service port 9280",
      'name: "{{ radar_k8s_release_name }}"' in ingress_tpl
      and "radar_k8s_service_port" in ingress_tpl)
check("ingress tls hosts present", "tls:" in ingress_tpl)
check("defaults require ingress class tailscale",
      "radar_k8s_tailscale_ingress_class: tailscale" in defaults)
check("reserved hostnames include tailscale-operator and rancher",
      "tailscale-operator" in defaults and "rancher" in defaults)
check("role asserts hostname not reserved",
      "radar_k8s_reserved_hostnames" in tasks)

print("\n== health and verification ==")
check("role probes /api/health over HTTPS",
      "/api/health" in tasks and "https://" in tasks)
check("role waits for ts-radar- proxy pod",
      "ts-radar-" in tasks)
check("playbook is standalone (not wired into master-stack)",
      "NOT wired into master-stack" in playbook
      or "roles:" in playbook and "include_role" not in playbook)
check("inventory group is radar_k8s",
      "[radar_k8s]" in hosts)
check("inventory hostname is radar",
      "radar_k8s_hostname: radar" in inv)

print("\n== helm lint / template ==")
lint = helm("lint", CHART)
check("helm lint passes", lint.returncode == 0, lint.stderr or lint.stdout[-200:])
tmpl = helm(
    "template", "radar", CHART,
    "--namespace", "radar",
    "-f", "/dev/null",
    "--set", "replicaCount=1",
    "--set", "image.tag=1.20.2",
    "--set", "ingress.enabled=false",
    "--set", "auth.mode=none",
    "--set", "service.type=ClusterIP",
    "--set", "rbac.helm=false",
)
check("helm template renders", tmpl.returncode == 0, tmpl.stderr[-300:])
if tmpl.returncode == 0:
    check("rendered Service is ClusterIP", "type: ClusterIP" in tmpl.stdout)
    check("rendered probe path is /api/health", "/api/health" in tmpl.stdout)
    check("no chart Ingress when disabled",
          "kind: Ingress" not in tmpl.stdout
          or tmpl.stdout.count("kind: Ingress") == 0)

print("\n== summary ==")
print("passed=%d failed=%d" % (passes, len(failures)))
if failures:
    for f in failures:
        print(" - %s" % f)
    sys.exit(1)
print("OK")
sys.exit(0)
