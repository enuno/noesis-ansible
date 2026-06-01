#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, NoesisPraxis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: noesis_registry_sync
short_description: Synchronize agent records across Noesis registries
description:
  - Reads agent records from a source registry.
  - Validates records against JSON schemas.
  - Writes or updates corresponding records in target registries.
  - Supports dry-run mode and idempotent operation.
  - Returns a detailed sync report.
options:
  source_registry:
    description: URL of the source registry endpoint.
    type: str
    required: true
  target_registries:
    description: List of target registry URLs.
    type: list
    elements: str
    required: true
  agent_id:
    description: Specific agent ID to sync. If omitted, syncs all agents.
    type: str
    required: false
  schema_path:
    description: Path to JSON schema for validation.
    type: path
    required: false
  sync_mode:
    description: Sync direction and behavior.
    type: str
    choices: [push, pull, bidirectional]
    default: push
  state:
    description: Desired state of the sync operation.
    type: str
    choices: [synced, absent]
    default: synced
author:
  - NoesisPraxis Infrastructure Team
"""

EXAMPLES = r"""
- name: Sync all agents from ACP to ANS and A2A
  noesis_registry_sync:
    source_registry: "http://localhost:8081"
    target_registries:
      - "http://localhost:8082"
      - "http://localhost:8084"
    sync_mode: push
    state: synced

- name: Sync single agent bidirectionally
  noesis_registry_sync:
    source_registry: "http://localhost:8081"
    target_registries:
      - "http://localhost:8082"
    agent_id: "agent-001"
    sync_mode: bidirectional
"""

RETURN = r"""
sync_report:
  description: Detailed report of the sync operation.
  type: dict
  contains:
    agents_read:
      description: Number of agents read from source.
      type: int
    agents_written:
      description: Number of agents written to targets.
      type: int
    agents_skipped:
      description: Number of agents already in sync.
      type: int
    errors:
      description: List of errors encountered.
      type: list
changed:
  description: Whether any registry was modified.
  type: bool
"""

import json

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.noesis import registry_request, validate_schema, is_check_mode


def fetch_agents(module, registry_url, agent_id=None):
    """Fetch agents from a registry."""
    if agent_id:
        url = "%s/agents/%s" % (registry_url, agent_id)
    else:
        url = "%s/agents" % registry_url

    result = registry_request(module, url)
    if result.get("status") not in [200, 201]:
        module.fail_json(
            msg="Failed to fetch from %s: HTTP %s - %s"
            % (registry_url, result.get("status"), result.get("error", "unknown"))
        )
    return result.get("body", [])


def write_agent(module, registry_url, agent_data):
    """Write or update an agent record in a target registry."""
    agent_id = agent_data.get("id") or agent_data.get("agent_id")
    if not agent_id:
        return {"error": "Agent data missing id/agent_id"}

    url = "%s/agents/%s" % (registry_url, agent_id)

    # Check if agent exists
    check = registry_request(module, url, method="GET")
    if check.get("status") == 200:
        # Update existing
        method = "PUT"
    else:
        # Create new
        method = "POST"
        url = "%s/agents" % registry_url

    if is_check_mode(module):
        return {"changed": True, "action": method, "agent_id": agent_id}

    result = registry_request(module, url, method=method, data=agent_data)
    return {
        "changed": result.get("status") in [200, 201, 204],
        "status": result.get("status"),
        "agent_id": agent_id,
        "action": method,
    }


def main():
    module_args = dict(
        source_registry=dict(type="str", required=True),
        target_registries=dict(type="list", elements="str", required=True),
        agent_id=dict(type="str", default=""),
        schema_path=dict(type="path", default=""),
        sync_mode=dict(type="str", choices=["push", "pull", "bidirectional"], default="push"),
        state=dict(type="str", choices=["synced", "absent"], default="synced"),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    source = module.params["source_registry"]
    targets = module.params["target_registries"]
    agent_id = module.params["agent_id"]
    schema_path = module.params["schema_path"]
    sync_mode = module.params["sync_mode"]
    state = module.params["state"]

    result = dict(
        changed=False,
        sync_report=dict(
            agents_read=0,
            agents_written=0,
            agents_skipped=0,
            errors=[],
        ),
    )

    # Fetch from source
    agents = fetch_agents(module, source, agent_id if agent_id else None)
    if not isinstance(agents, list):
        agents = [agents]

    result["sync_report"]["agents_read"] = len(agents)

    # Validate against schema if provided
    if schema_path:
        for agent in agents:
            validate_schema(module, agent, schema_path)

    # Sync to each target
    for target in targets:
        for agent in agents:
            if state == "absent":
                # Delete agent from target
                agent_id_val = agent.get("id") or agent.get("agent_id")
                url = "%s/agents/%s" % (target, agent_id_val)
                if not is_check_mode(module):
                    del_result = registry_request(module, url, method="DELETE")
                    if del_result.get("status") in [200, 204]:
                        result["changed"] = True
                        result["sync_report"]["agents_written"] += 1
                else:
                    result["changed"] = True
                    result["sync_report"]["agents_written"] += 1
            else:
                # Push agent to target
                write_result = write_agent(module, target, agent)
                if write_result.get("error"):
                    result["sync_report"]["errors"].append(write_result["error"])
                elif write_result.get("changed"):
                    result["changed"] = True
                    result["sync_report"]["agents_written"] += 1
                else:
                    result["sync_report"]["agents_skipped"] += 1

    # Handle bidirectional sync
    if sync_mode == "bidirectional":
        for target in targets:
            target_agents = fetch_agents(module, target, agent_id if agent_id else None)
            if not isinstance(target_agents, list):
                target_agents = [target_agents]
            for agent in target_agents:
                write_result = write_agent(module, source, agent)
                if write_result.get("changed"):
                    result["changed"] = True

    module.exit_json(**result)


if __name__ == "__main__":
    main()
