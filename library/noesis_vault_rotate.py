#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, NoesisPraxis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: noesis_vault_rotate
short_description: Rotate secrets in Ansible Vault-managed files
description:
  - Reads secrets from a Vault-managed YAML file.
  - Generates new values or fetches replacements from Bitwarden.
  - Updates the Vault file and re-encrypts.
  - Tracks rotation metadata.
options:
  vault_file:
    description: Path to the Vault-managed YAML file.
    type: path
    required: true
  vault_password_file:
    description: Path to the Ansible Vault password file.
    type: path
    required: true
  secret_keys:
    description: List of keys to rotate.
    type: list
    elements: str
    required: true
  rotation_strategy:
    description: How to generate new values.
    type: str
    choices: [random, bws_fetch, manual]
    default: random
  bws_config:
    description: Bitwarden config for bws_fetch strategy.
    type: dict
    required: false
  secret_length:
    description: Length for randomly generated secrets.
    type: int
    default: 32
  state:
    description: Desired state.
    type: str
    choices: [rotated, present]
    default: rotated
author:
  - NoesisPraxis Infrastructure Team
"""

EXAMPLES = r"""
- name: Rotate all secrets in vault file
  noesis_vault_rotate:
    vault_file: "/opt/noesispraxis/secrets/api-keys.yml"
    vault_password_file: "~/projects/noesis-ansible/.vault_pass"
    secret_keys:
      - api_key_primary
      - api_key_secondary
    rotation_strategy: random
    secret_length: 48

- name: Rotate from Bitwarden
  noesis_vault_rotate:
    vault_file: "/opt/noesispraxis/secrets/telegram.yml"
    vault_password_file: "~/projects/noesis-ansible/.vault_pass"
    secret_keys:
      - telegram_bot_token
    rotation_strategy: bws_fetch
    bws_config:
      org_id: "93331de5-fa6e-44ab-8aee-b3840034e681"
      project_id: "7173d0ef-7c7d-4356-b98f-b3d20010b2e7"
      bws_cli_path: "~/.local/bin/bws"
"""

RETURN = r"""
rotated_keys:
  description: List of keys that were rotated.
  type: list
skipped_keys:
  description: List of keys that were skipped.
  type: list
rotation_timestamp:
  description: ISO timestamp of the rotation.
  type: str
changed:
  description: Whether any secrets were rotated.
  type: bool
"""

import os
import secrets
import string

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.noesis import (
    vault_encrypt_file,
    vault_decrypt_file,
    load_yaml_file,
    write_yaml_file,
    is_check_mode,
)


def generate_random_secret(length=32):
    """Generate a cryptographically secure random secret."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_+="
    return "".join(secrets.choice(alphabet) for _ in range(length))


def fetch_from_bitwarden(module, bws_config, secret_key):
    """Fetch a secret value from Bitwarden Secrets Manager."""
    import subprocess
    import json

    bws_path = os.path.expanduser(bws_config.get("bws_cli_path", "~/.local/bin/bws"))
    org_id = bws_config.get("org_id", "")
    project_id = bws_config.get("project_id", "")

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
        secrets_list = json.loads(result.stdout)
        for secret in secrets_list:
            if secret.get("key") == secret_key:
                return secret.get("value", "")
        module.fail_json(msg="Secret '%s' not found in Bitwarden" % secret_key)
    except Exception as e:
        module.fail_json(msg="Failed to fetch from Bitwarden: %s" % str(e))


def main():
    module_args = dict(
        vault_file=dict(type="path", required=True),
        vault_password_file=dict(type="path", required=True),
        secret_keys=dict(type="list", elements="str", required=True),
        rotation_strategy=dict(type="str", choices=["random", "bws_fetch", "manual"], default="random"),
        bws_config=dict(type="dict", default={}),
        secret_length=dict(type="int", default=32),
        state=dict(type="str", choices=["rotated", "present"], default="rotated"),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    vault_file = os.path.expanduser(module.params["vault_file"])
    vault_password_file = os.path.expanduser(module.params["vault_password_file"])
    secret_keys = module.params["secret_keys"]
    rotation_strategy = module.params["rotation_strategy"]
    bws_config = module.params["bws_config"]
    secret_length = module.params["secret_length"]
    state = module.params["state"]

    result = dict(
        changed=False,
        rotated_keys=[],
        skipped_keys=[],
        rotation_timestamp="",
    )

    # Validate vault file exists
    if not os.path.exists(vault_file):
        module.fail_json(msg="Vault file not found: %s" % vault_file)

    if not os.path.exists(vault_password_file):
        module.fail_json(msg="Vault password file not found: %s" % vault_password_file)

    # Decrypt vault file
    if not is_check_mode(module):
        vault_decrypt_file(module, vault_file, vault_password_file)
        data = load_yaml_file(vault_file)
    else:
        data = {}

    # Rotate each key
    for key in secret_keys:
        if key not in data and state == "present":
            result["skipped_keys"].append(key)
            continue

        if rotation_strategy == "random":
            new_value = generate_random_secret(secret_length)
        elif rotation_strategy == "bws_fetch":
            new_value = fetch_from_bitwarden(module, bws_config, key)
        elif rotation_strategy == "manual":
            # In manual mode, we just mark for rotation but don't generate
            result["skipped_keys"].append(key)
            continue

        if not is_check_mode(module):
            data[key] = new_value

        result["rotated_keys"].append(key)
        result["changed"] = True

    # Update metadata
    if result["changed"] and not is_check_mode(module):
        import datetime
        result["rotation_timestamp"] = datetime.datetime.utcnow().isoformat() + "Z"
        data["_noesis_rotation_meta"] = {
            "rotated_at": result["rotation_timestamp"],
            "rotated_keys": result["rotated_keys"],
            "strategy": rotation_strategy,
        }
        write_yaml_file(vault_file, data)
        vault_encrypt_file(module, vault_file, vault_password_file)

    module.exit_json(**result)


if __name__ == "__main__":
    main()
