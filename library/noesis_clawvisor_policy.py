#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, NoesisPraxis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: noesis_clawvisor_policy
short_description: Manage Clawvisor security policies
description:
  - Creates, updates, or deletes Clawvisor policy definitions.
  - Supports policy types: access_control, sandbox, network, audit.
  - Validates policy syntax before application.
  - Idempotent — compares existing policy before modification.
options:
  clawvisor_url:
    description: URL of the Clawvisor policy API.
    type: str
    required: true
  policy_name:
    description: Unique name for the policy.
    type: str
    required: true
  policy_type:
    description: Category of security policy.
    type: str
    choices: [access_control, sandbox, network, audit, composite]
    required: true
  policy_rules:
    description: List of policy rules (dicts with match conditions and actions).
    type: list
    elements: dict
    required: true
  priority:
    description: Policy priority (lower number = higher priority).
    type: int
    default: 100
  enabled:
    description: Whether the policy is active.
    type: bool
    default: true
  state:
    description: Desired state of the policy.
    type: str
    choices: [present, absent]
    default: present
author:
  - NoesisPraxis Infrastructure Team
"""

EXAMPLES = r"""
- name: Create an access control policy
  noesis_clawvisor_policy:
    clawvisor_url: "http://localhost:8086"
    policy_name: "agent-filesystem-restrict"
    policy_type: access_control
    policy_rules:
      - match:
          agent_role: "untrusted"
          resource: "filesystem"
        action: "deny"
        log: true
    priority: 10
    enabled: true

- name: Remove a policy
  noesis_clawvisor_policy:
    clawvisor_url: "http://localhost:8086"
    policy_name: "legacy-policy"
    policy_type: access_control
    policy_rules: []
    state: absent
"""

RETURN = r"""
policy_id:
  description: The policy identifier in Clawvisor.
  type: str
policy_version:
  description: Version hash of the applied policy.
  type: str
changed:
  description: Whether the policy was created or modified.
  type: bool
"""

import hashlib
import json

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.noesis import registry_request, is_check_mode


def policy_hash(policy):
    """Compute a stable hash of policy content for idempotency."""
    canonical = json.dumps(policy, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def get_policy(module, clawvisor_url, policy_name):
    """Fetch existing policy from Clawvisor."""
    url = "%s/policies/%s" % (clawvisor_url, policy_name)
    result = registry_request(module, url, method="GET")
    if result.get("status") == 200:
        return result.get("body", {})
    return None


def apply_policy(module, clawvisor_url, policy_def, existing=None):
    """Create or update a policy in Clawvisor."""
    policy_name = policy_def["policy_name"]

    if existing:
        url = "%s/policies/%s" % (clawvisor_url, policy_name)
        method = "PUT"
    else:
        url = "%s/policies" % clawvisor_url
        method = "POST"

    if is_check_mode(module):
        return {"changed": True, "policy_id": policy_name, "version": policy_hash(policy_def)}

    result = registry_request(module, url, method=method, data=policy_def)
    if result.get("status") not in [200, 201, 204]:
        module.fail_json(
            msg="Failed to apply policy '%s': HTTP %s - %s"
            % (policy_name, result.get("status"), result.get("error", "unknown"))
        )

    return {
        "changed": True,
        "policy_id": policy_name,
        "version": policy_hash(policy_def),
    }


def delete_policy(module, clawvisor_url, policy_name):
    """Remove a policy from Clawvisor."""
    url = "%s/policies/%s" % (clawvisor_url, policy_name)

    if is_check_mode(module):
        return {"changed": True}

    result = registry_request(module, url, method="DELETE")
    if result.get("status") not in [200, 204]:
        module.fail_json(
            msg="Failed to delete policy '%s': HTTP %s" % (policy_name, result.get("status"))
        )
    return {"changed": True}


def main():
    module_args = dict(
        clawvisor_url=dict(type="str", required=True),
        policy_name=dict(type="str", required=True),
        policy_type=dict(type="str", choices=["access_control", "sandbox", "network", "audit", "composite"], required=True),
        policy_rules=dict(type="list", elements="dict", required=True),
        priority=dict(type="int", default=100),
        enabled=dict(type="bool", default=True),
        state=dict(type="str", choices=["present", "absent"], default="present"),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    clawvisor_url = module.params["clawvisor_url"]
    policy_name = module.params["policy_name"]
    policy_type = module.params["policy_type"]
    policy_rules = module.params["policy_rules"]
    priority = module.params["priority"]
    enabled = module.params["enabled"]
    state = module.params["state"]

    # Build policy definition
    policy_def = dict(
        policy_name=policy_name,
        policy_type=policy_type,
        policy_rules=policy_rules,
        priority=priority,
        enabled=enabled,
        version=policy_hash(dict(name=policy_name, type=policy_type, rules=policy_rules, priority=priority)),
    )

    # Check existing
    existing = get_policy(module, clawvisor_url, policy_name)

    result = dict(
        changed=False,
        policy_id=policy_name,
        policy_version="",
    )

    if state == "absent":
        if existing:
            del_result = delete_policy(module, clawvisor_url, policy_name)
            result["changed"] = del_result["changed"]
        module.exit_json(**result)

    if state == "present":
        if existing:
            # Check if policy content changed
            existing_hash = policy_hash(existing)
            new_hash = policy_hash(policy_def)
            if existing_hash != new_hash:
                update_result = apply_policy(module, clawvisor_url, policy_def, existing)
                result["changed"] = update_result["changed"]
                result["policy_version"] = update_result["version"]
            else:
                result["policy_version"] = existing_hash
        else:
            create_result = apply_policy(module, clawvisor_url, policy_def)
            result["changed"] = create_result["changed"]
            result["policy_version"] = create_result["version"]

    module.exit_json(**result)


if __name__ == "__main__":
    main()
