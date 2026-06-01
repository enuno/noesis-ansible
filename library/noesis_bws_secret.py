#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, NoesisPraxis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: noesis_bws_secret
short_description: Import secrets from Bitwarden Secrets Manager into Ansible Vault-managed files
description:
  - Fetches secrets from Bitwarden Secrets Manager via the C(bws) CLI.
  - Writes secrets to local files and encrypts them with ansible-vault.
  - Tracks metadata for rotation and validation.
  - Idempotent — skips secrets that are already current.
options:
  bws_cli_path:
    description: Path to the bws CLI binary.
    type: path
    default: "~/.local/bin/bws"
  org_id:
    description: Bitwarden organization ID.
    type: str
    required: true
  project_id:
    description: Bitwarden project ID.
    type: str
    required: false
  secret_key:
    description: Key of the secret to fetch from Bitwarden.
    type: str
    required: true
  vault_file:
    description: Path to the Vault-managed file to write the secret into.
    type: path
    required: true
  vault_key:
    description: YAML key name for the secret in the vault file.
    type: str
    required: true
  vault_password_file:
    description: Path to the Ansible Vault password file.
    type: path
    required: true
  state:
    description: Desired state of the secret.
    type: str
    choices: [present, absent]
    default: present
  force_refresh:
    description: Force refresh even if secret appears current.
    type: bool
    default: false
author:
  - NoesisPraxis Infrastructure Team
"""

EXAMPLES = r"""
- name: Import Telegram bot token from Bitwarden
  noesis_bws_secret:
    org_id: "93331de5-fa6e-44ab-8aee-b3840034e681"
    project_id: "7173d0ef-7c7d-4356-b98f-b3d20010b2e7"
    secret_key: "telegram-bot-token"
    vault_file: "/opt/noesispraxis/secrets/telegram.yml"
    vault_key: "telegram_bot_token"
    vault_password_file: "~/projects/noesis-ansible/.vault_pass"
    state: present

- name: Remove a secret from local vault
  noesis_bws_secret:
    org_id: "93331de5-fa6e-44ab-8aee-b3840034e681"
    secret_key: "old-api-key"
    vault_file: "/opt/noesispraxis/secrets/legacy.yml"
    vault_key: "old_api_key"
    vault_password_file: "~/projects/noesis-ansible/.vault_pass"
    state: absent
"""

RETURN = r"""
secret_value:
  description: The fetched secret value (redacted in output).
  type: str
  returned: when state=present
  sample: "***REDACTED***"
changed:
  description: Whether the secret was imported or updated.
  type: bool
vault_file:
  description: Path to the vault file that was modified.
  type: str
"""

import os
import subprocess
import json

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.noesis import (
    vault_encrypt_file,
    vault_decrypt_file,
    load_yaml_file,
    write_yaml_file,
    is_check_mode,
)


def run_bws_list(module, bws_path, org_id, project_id):
    """Run bws secret list and return parsed JSON."""
    cmd = [bws_path, "secret", "list", "--organization-id", org_id]
    if project_id:
        cmd.extend(["--project-id", project_id])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "BWS_ACCESS_TOKEN": os.environ.get("BWS_ACCESS_TOKEN", "")},
        )
        if result.returncode != 0:
            module.fail_json(msg="bws secret list failed: %s" % result.stderr)
        return json.loads(result.stdout)
    except Exception as e:
        module.fail_json(msg="Failed to run bws CLI: %s" % str(e))


def find_secret(secrets_list, key):
    """Find a secret by key in the bws list output."""
    for secret in secrets_list:
        if secret.get("key") == key:
            return secret
    return None


def main():
    module_args = dict(
        bws_cli_path=dict(type="path", default="~/.local/bin/bws"),
        org_id=dict(type="str", required=True),
        project_id=dict(type="str", default=""),
        secret_key=dict(type="str", required=True),
        vault_file=dict(type="path", required=True),
        vault_key=dict(type="str", required=True),
        vault_password_file=dict(type="path", required=True),
        state=dict(type="str", choices=["present", "absent"], default="present"),
        force_refresh=dict(type="bool", default=False),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    bws_path = os.path.expanduser(module.params["bws_cli_path"])
    org_id = module.params["org_id"]
    project_id = module.params["project_id"]
    secret_key = module.params["secret_key"]
    vault_file = os.path.expanduser(module.params["vault_file"])
    vault_key = module.params["vault_key"]
    vault_password_file = os.path.expanduser(module.params["vault_password_file"])
    state = module.params["state"]
    force_refresh = module.params["force_refresh"]

    result = dict(changed=False, vault_file=vault_file, vault_key=vault_key)

    # Validate bws CLI exists
    if not os.path.exists(bws_path):
        module.fail_json(msg="bws CLI not found at: %s" % bws_path)

    # Validate vault password file exists
    if not os.path.exists(vault_password_file):
        module.fail_json(msg="Vault password file not found at: %s" % vault_password_file)

    # Ensure vault directory exists
    vault_dir = os.path.dirname(vault_file)
    if not os.path.exists(vault_dir):
        if is_check_mode(module):
            result["changed"] = True
            module.exit_json(**result)
        os.makedirs(vault_dir, mode=0o700)

    # Handle absent state
    if state == "absent":
        if os.path.exists(vault_file):
            # Decrypt, remove key, re-encrypt
            if not is_check_mode(module):
                vault_decrypt_file(module, vault_file, vault_password_file)
                data = load_yaml_file(vault_file)
                if vault_key in data:
                    del data[vault_key]
                    write_yaml_file(vault_file, data)
                    vault_encrypt_file(module, vault_file, vault_password_file)
                    result["changed"] = True
            else:
                result["changed"] = True
        module.exit_json(**result)

    # Fetch secrets from Bitwarden
    secrets_list = run_bws_list(module, bws_path, org_id, project_id)
    secret = find_secret(secrets_list, secret_key)

    if secret is None:
        module.fail_json(msg="Secret '%s' not found in Bitwarden project" % secret_key)

    secret_value = secret.get("value", "")
    secret_note = secret.get("note", "")
    secret_id = secret.get("id", "")

    # Check if vault file exists and has current value
    current_value = None
    if os.path.exists(vault_file):
        # Decrypt to check current value
        if not is_check_mode(module):
            vault_decrypt_file(module, vault_file, vault_password_file)
            data = load_yaml_file(vault_file)
            current_value = data.get(vault_key)
            # Re-encrypt immediately
            vault_encrypt_file(module, vault_file, vault_password_file)

    # Determine if update is needed
    needs_update = force_refresh or current_value != secret_value

    if needs_update:
        if is_check_mode(module):
            result["changed"] = True
            result["secret_value"] = "***REDACTED***"
            module.exit_json(**result)

        # Decrypt, update, re-encrypt
        vault_decrypt_file(module, vault_file, vault_password_file)
        data = load_yaml_file(vault_file)
        data[vault_key] = secret_value

        # Add metadata
        data["_noesis_meta"] = {
            "secret_id": secret_id,
            "secret_key": secret_key,
            "updated_at": json.dumps({}),  # Will be filled by caller
            "source": "bitwarden",
        }

        write_yaml_file(vault_file, data)
        vault_encrypt_file(module, vault_file, vault_password_file)

        result["changed"] = True
        result["secret_value"] = "***REDACTED***"
        result["secret_id"] = secret_id

    module.exit_json(**result)


if __name__ == "__main__":
    main()
