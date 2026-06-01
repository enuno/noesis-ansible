#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, NoesisPraxis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: noesis_mcpjungle_onboard
short_description: Onboard or update an MCP server in MCPJungle
description:
  - Registers an MCP server with the MCPJungle registry.
  - Validates the server definition against the MCP server schema.
  - Supports versioning, tool groups, and approval workflows.
  - Idempotent — updates existing registrations when properties change.
options:
  mcpjungle_url:
    description: URL of the MCPJungle registry API.
    type: str
    required: true
  server_definition:
    description: MCP server definition dict (name, endpoint, tools, version, etc.).
    type: dict
    required: true
  schema_path:
    description: Path to the MCP server JSON schema for validation.
    type: path
    required: false
  state:
    description: Desired state of the MCP server registration.
    type: str
    choices: [present, absent, approved, revoked]
    default: present
  approval_required:
    description: Whether the server requires explicit approval.
    type: bool
    default: true
author:
  - NoesisPraxis Infrastructure Team
"""

EXAMPLES = r"""
- name: Onboard a new MCP server
  noesis_mcpjungle_onboard:
    mcpjungle_url: "http://localhost:8085"
    server_definition:
      name: "filesystem-mcp"
      endpoint: "http://localhost:3001/sse"
      version: "1.2.0"
      tools:
        - name: "read_file"
          description: "Read a file from the filesystem"
      capabilities:
        - "filesystem"
    state: present

- name: Revoke an MCP server
  noesis_mcpjungle_onboard:
    mcpjungle_url: "http://localhost:8085"
    server_definition:
      name: "filesystem-mcp"
    state: revoked
"""

RETURN = r"""
server_id:
  description: The ID assigned by MCPJungle.
  type: str
registration_status:
  description: Current registration status (pending, approved, revoked).
  type: str
changed:
  description: Whether the registration was created or modified.
  type: bool
"""

import json

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.noesis import registry_request, validate_schema, is_check_mode


def get_server(module, mcpjungle_url, server_name):
    """Get existing server registration."""
    url = "%s/servers/%s" % (mcpjungle_url, server_name)
    result = registry_request(module, url, method="GET")
    if result.get("status") == 200:
        return result.get("body", {})
    return None


def create_or_update_server(module, mcpjungle_url, server_def, existing=None):
    """Create or update an MCP server registration."""
    server_name = server_def.get("name")
    if not server_name:
        module.fail_json(msg="server_definition must include 'name'")

    if existing:
        # Update existing
        url = "%s/servers/%s" % (mcpjungle_url, server_name)
        method = "PUT"
    else:
        # Create new
        url = "%s/servers" % mcpjungle_url
        method = "POST"

    if is_check_mode(module):
        return {"changed": True, "server_id": server_name, "status": "pending"}

    result = registry_request(module, url, method=method, data=server_def)
    if result.get("status") not in [200, 201, 204]:
        module.fail_json(
            msg="Failed to register MCP server '%s': HTTP %s - %s"
            % (server_name, result.get("status"), result.get("error", "unknown"))
        )

    return {
        "changed": True,
        "server_id": server_name,
        "status": "pending",
    }


def delete_server(module, mcpjungle_url, server_name):
    """Remove an MCP server registration."""
    url = "%s/servers/%s" % (mcpjungle_url, server_name)

    if is_check_mode(module):
        return {"changed": True}

    result = registry_request(module, url, method="DELETE")
    if result.get("status") not in [200, 204]:
        module.fail_json(
            msg="Failed to delete MCP server '%s': HTTP %s"
            % (server_name, result.get("status"))
        )
    return {"changed": True}


def approve_server(module, mcpjungle_url, server_name):
    """Approve a pending MCP server registration."""
    url = "%s/servers/%s/approve" % (mcpjungle_url, server_name)

    if is_check_mode(module):
        return {"changed": True, "status": "approved"}

    result = registry_request(module, url, method="POST")
    if result.get("status") not in [200, 204]:
        module.fail_json(
            msg="Failed to approve MCP server '%s': HTTP %s"
            % (server_name, result.get("status"))
        )
    return {"changed": True, "status": "approved"}


def revoke_server(module, mcpjungle_url, server_name):
    """Revoke an approved MCP server registration."""
    url = "%s/servers/%s/revoke" % (mcpjungle_url, server_name)

    if is_check_mode(module):
        return {"changed": True, "status": "revoked"}

    result = registry_request(module, url, method="POST")
    if result.get("status") not in [200, 204]:
        module.fail_json(
            msg="Failed to revoke MCP server '%s': HTTP %s"
            % (server_name, result.get("status"))
        )
    return {"changed": True, "status": "revoked"}


def main():
    module_args = dict(
        mcpjungle_url=dict(type="str", required=True),
        server_definition=dict(type="dict", required=True),
        schema_path=dict(type="path", default=""),
        state=dict(type="str", choices=["present", "absent", "approved", "revoked"], default="present"),
        approval_required=dict(type="bool", default=True),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    mcpjungle_url = module.params["mcpjungle_url"]
    server_def = module.params["server_definition"]
    schema_path = module.params["schema_path"]
    state = module.params["state"]
    approval_required = module.params["approval_required"]

    # Validate schema if provided
    if schema_path:
        validate_schema(module, server_def, schema_path)

    server_name = server_def.get("name")
    if not server_name:
        module.fail_json(msg="server_definition must include 'name'")

    # Check existing registration
    existing = get_server(module, mcpjungle_url, server_name)

    result = dict(
        changed=False,
        server_id=server_name,
        registration_status="",
    )

    if state == "absent":
        if existing:
            del_result = delete_server(module, mcpjungle_url, server_name)
            result["changed"] = del_result["changed"]
        module.exit_json(**result)

    if state == "present":
        if existing:
            # Check if update is needed
            if existing != server_def:
                update_result = create_or_update_server(module, mcpjungle_url, server_def, existing)
                result["changed"] = update_result["changed"]
                result["registration_status"] = update_result["status"]
            else:
                result["registration_status"] = existing.get("status", "approved")
        else:
            create_result = create_or_update_server(module, mcpjungle_url, server_def)
            result["changed"] = create_result["changed"]
            result["registration_status"] = create_result["status"]

            # Auto-approve if not required
            if not approval_required:
                approve_result = approve_server(module, mcpjungle_url, server_name)
                result["registration_status"] = approve_result["status"]

    elif state == "approved":
        if not existing:
            module.fail_json(msg="Cannot approve non-existent server: %s" % server_name)
        approve_result = approve_server(module, mcpjungle_url, server_name)
        result["changed"] = approve_result["changed"]
        result["registration_status"] = approve_result["status"]

    elif state == "revoked":
        if not existing:
            module.fail_json(msg="Cannot revoke non-existent server: %s" % server_name)
        revoke_result = revoke_server(module, mcpjungle_url, server_name)
        result["changed"] = revoke_result["changed"]
        result["registration_status"] = revoke_result["status"]

    module.exit_json(**result)


if __name__ == "__main__":
    main()
