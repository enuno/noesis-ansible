"""Offline validation for Rancher full-remove path.

Non-mutating. Run:
  /usr/bin/python3 tests/rancher_k8s_remove/test_offline.py
"""

from __future__ import annotations

import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ROLE = os.path.join(REPO, "roles", "rancher_k8s_remove")
PLAYBOOK = os.path.join(REPO, "playbooks", "rancher-k8s-remove.yml")

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


defaults = read(os.path.join(ROLE, "defaults", "main.yml"))
tasks = read(os.path.join(ROLE, "tasks", "main.yml"))
playbook = read(PLAYBOOK)

print("== gate ==")
check("remove gate defaults false",
      "rancher_k8s_remove_enabled: false" in defaults)
check("role asserts enable gate",
      "rancher_k8s_remove_enabled | bool" in tasks)
check("playbook documents -e enable",
      "rancher_k8s_remove_enabled=true" in playbook)

print("\n== release coverage ==")
for rel in (
    "rancher",
    "rancher-webhook",
    "system-upgrade-controller",
    "rancher-turtles",
    "fleet-agent-local",
    "fleet",
    "fleet-crd",
):
    check("targets helm release %s" % rel, "name: %s" % rel in defaults)

print("\n== safety ==")
check("denies kube-system", "kube-system" in defaults)
check("denies tailscale", "tailscale" in defaults)
check("denies radar", "- radar" in defaults)
check("denies mcpjungle", "mcpjungle" in defaults)
check("CRD deny list keeps k3s helm CRDs",
      "k3s.cattle.io" in defaults
      and "helmcharts.helm.cattle.io" in defaults)
check("does not claim Bitwarden secret deletion",
      "bitwarden" not in tasks.lower() and "bws" not in tasks.lower())

print("\n== summary ==")
print("passed=%d failed=%d" % (passes, len(failures)))
if failures:
    for f in failures:
        print(" - %s" % f)
    sys.exit(1)
print("OK")
sys.exit(0)
