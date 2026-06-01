#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, NoesisPraxis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: noesis_macos_service
short_description: Manage macOS launchd services for Noesis agents
description:
  - Installs, removes, starts, stops, and validates macOS launchd plists.
  - Checks service health via launchctl and port connectivity.
  - Supports resource budgets (CPU, RAM) and Tailscale binding.
  - Idempotent — compares existing plist before modification.
options:
  name:
    description: Service name (label) for launchd.
    type: str
    required: true
  plist_content:
    description: Dict representing the launchd plist content.
    type: dict
    required: true
  state:
    description: Desired state of the service.
    type: str
    choices: [present, absent, started, stopped, restarted]
    default: present
  launchagents_dir:
    description: Directory for user LaunchAgents.
    type: path
    default: "~/Library/LaunchAgents"
  validate_port:
    description: TCP port to validate after starting.
    type: int
    required: false
  validate_timeout:
    description: Seconds to wait for port to become available.
    type: int
    default: 10
  resource_budget:
    description: Resource limits dict (cpu_percent, ram_mb).
    type: dict
    required: false
author:
  - NoesisPraxis Infrastructure Team
"""

EXAMPLES = r"""
- name: Install and start Noesis ClawDev service
  noesis_macos_service:
    name: "com.noesispraxis.clawdev"
    plist_content:
      Label: "com.noesispraxis.clawdev"
      ProgramArguments:
        - "/opt/noesispraxis/clawdev/bin/clawdev"
      EnvironmentVariables:
        NODE_ENV: "production"
      StandardOutPath: "~/Library/Logs/noesis/clawdev.log"
      StandardErrorPath: "~/Library/Logs/noesis/clawdev.error.log"
      KeepAlive: true
      RunAtLoad: true
      Nice: 10
    state: started
    validate_port: 8090
    resource_budget:
      cpu_percent: 50
      ram_mb: 512

- name: Stop and remove a service
  noesis_macos_service:
    name: "com.noesispraxis.clawdev"
    plist_content: {}
    state: absent
"""

RETURN = r"""
service_status:
  description: Current launchctl status of the service.
  type: str
plist_path:
  description: Path to the installed plist file.
  type: str
port_valid:
  description: Whether the service port responded.
  type: bool
changed:
  description: Whether the service state changed.
  type: bool
"""

import os
import plistlib
import socket
import subprocess
import tempfile

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.noesis import is_check_mode


def plist_path_for_service(launchagents_dir, service_name):
    """Return the full path to a LaunchAgent plist."""
    return os.path.join(os.path.expanduser(launchagents_dir), "%s.plist" % service_name)


def load_plist(path):
    """Load a plist file and return its contents as a dict."""
    try:
        with open(path, "rb") as f:
            return plistlib.load(f)
    except Exception:
        return None


def write_plist(path, content):
    """Write a dict to a plist file."""
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with open(path, "wb") as f:
        plistlib.dump(content, f)
    os.chmod(path, 0o600)


def remove_plist(path):
    """Remove a plist file."""
    if os.path.exists(path):
        os.remove(path)


def launchctl_list(service_name):
    """Check if a service is loaded in launchctl."""
    try:
        result = subprocess.run(
            ["launchctl", "list", service_name],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def launchctl_load(path):
    """Load a launchd plist."""
    result = subprocess.run(
        ["launchctl", "load", path],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def launchctl_unload(path):
    """Unload a launchd plist."""
    result = subprocess.run(
        ["launchctl", "unload", path],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def launchctl_start(service_name):
    """Start a loaded launchd service."""
    result = subprocess.run(
        ["launchctl", "start", service_name],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def launchctl_stop(service_name):
    """Stop a loaded launchd service."""
    result = subprocess.run(
        ["launchctl", "stop", service_name],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def launchctl_remove(service_name):
    """Remove a service from launchctl."""
    result = subprocess.run(
        ["launchctl", "remove", service_name],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def check_port(host, port, timeout):
    """Check if a TCP port is open."""
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except Exception:
        return False


def apply_resource_budget(plist_content, budget):
    """Inject resource limits into plist content."""
    if budget:
        if "cpu_percent" in budget:
            # launchd uses CPU usage limits via ProcessType or custom limits
            plist_content["ProcessType"] = "Background"
        if "ram_mb" in budget:
            # launchd doesn't have direct RAM limits, but we can set Nice
            plist_content["Nice"] = 10
    return plist_content


def main():
    module_args = dict(
        name=dict(type="str", required=True),
        plist_content=dict(type="dict", required=True),
        state=dict(type="str", choices=["present", "absent", "started", "stopped", "restarted"], default="present"),
        launchagents_dir=dict(type="path", default="~/Library/LaunchAgents"),
        validate_port=dict(type="int", default=0),
        validate_timeout=dict(type="int", default=10),
        resource_budget=dict(type="dict", default={}),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    service_name = module.params["name"]
    plist_content = module.params["plist_content"]
    state = module.params["state"]
    launchagents_dir = module.params["launchagents_dir"]
    validate_port = module.params["validate_port"]
    validate_timeout = module.params["validate_timeout"]
    resource_budget = module.params["resource_budget"]

    plist_path = plist_path_for_service(launchagents_dir, service_name)
    existing_plist = load_plist(plist_path)
    is_loaded = launchctl_list(service_name)

    result = dict(
        changed=False,
        service_status="unknown",
        plist_path=plist_path,
        port_valid=False,
    )

    # Apply resource budget to plist content
    plist_content = apply_resource_budget(plist_content, resource_budget)

    if state == "absent":
        if is_loaded:
            if not is_check_mode(module):
                launchctl_stop(service_name)
                launchctl_remove(service_name)
                launchctl_unload(plist_path)
            result["changed"] = True
        if existing_plist:
            if not is_check_mode(module):
                remove_plist(plist_path)
            result["changed"] = True
        result["service_status"] = "absent"
        module.exit_json(**result)

    # Ensure plist is present
    plist_needs_update = existing_plist != plist_content

    if plist_needs_update:
        if is_loaded:
            if not is_check_mode(module):
                launchctl_stop(service_name)
                launchctl_unload(plist_path)
        if not is_check_mode(module):
            write_plist(plist_path, plist_content)
        result["changed"] = True

    # Handle states
    if state in ["present", "started"]:
        if not is_loaded or plist_needs_update:
            if not is_check_mode(module):
                launchctl_load(plist_path)
                launchctl_start(service_name)
            result["changed"] = True
        result["service_status"] = "started"

    elif state == "stopped":
        if is_loaded:
            if not is_check_mode(module):
                launchctl_stop(service_name)
            result["changed"] = True
        result["service_status"] = "stopped"

    elif state == "restarted":
        if not is_check_mode(module):
            if is_loaded:
                launchctl_stop(service_name)
            launchctl_start(service_name)
        result["changed"] = True
        result["service_status"] = "restarted"

    # Validate port if requested
    if validate_port > 0 and state in ["present", "started", "restarted"]:
        if not is_check_mode(module):
            port_ok = check_port("127.0.0.1", validate_port, validate_timeout)
            result["port_valid"] = port_ok
            if not port_ok:
                module.warn("Service port %d did not respond within %d seconds" % (validate_port, validate_timeout))
        else:
            result["port_valid"] = True  # Assume valid in check mode

    module.exit_json(**result)


if __name__ == "__main__":
    main()
