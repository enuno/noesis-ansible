#!/usr/bin/env python3
"""Resolve UniFi deployment secrets with the official Bitwarden SM SDK.

Input JSON on stdin, output JSON on stdout. Never put secret values in argv.
Only invoked by no_log Ansible tasks; do not run from an interactive terminal.
"""
import json
import os
import secrets
import sys
import base64
from uuid import UUID


GENERATED = ("MCP_AUTH_TOKEN", "UNIFI_AUDIT_CHAIN_KEY",
             "UNIFI_FLEET_CREDENTIAL_KEY", "POSTGRES_PASSWORD", "RUNTIME_PASSWORD",
             "REDIS_PASSWORD")


def resolve(client, project_id, organization_id, keys, record_ids, create):
    # Project get verifies that the machine account can see the intended project.
    project = client.projects().get(str(project_id)).data
    if UUID(str(project.organization_id)) != organization_id:
        raise ValueError("project does not belong to the configured organization")
    listed = client.secrets().list(str(organization_id)).data.data
    results = {}
    created = []
    for name, key in keys.items():
        matches = [entry for entry in listed if entry.key == key
                   and project_id in [UUID(str(p)) for p in entry.project_ids]]
        pinned = record_ids.get(name)
        if pinned:
            matches = [entry for entry in matches if str(entry.id) == str(UUID(pinned))]
            if len(matches) != 1:
                raise ValueError(f"pinned record missing for {name}")
        elif len(matches) > 1:
            raise ValueError(f"ambiguous Bitwarden key for {name}; pin an id")
        if matches:
            item = client.secrets().get(str(matches[0].id)).data
            if key != item.key or project_id != UUID(str(item.project_id)):
                raise ValueError(f"record not in expected project for {name}")
        elif name in GENERATED and create:
            # No argv exposure. Generation happens immediately before SDK write;
            # a failed response stops the run. Next run lists first, never rotates.
            value = (base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
                     if name == "UNIFI_FLEET_CREDENTIAL_KEY" else secrets.token_hex(32))
            item = client.secrets().create(organization_id, key, value, None,
                                           [project_id]).data
            verified = client.secrets().get(str(item.id)).data
            if verified.key != key or verified.value != value:
                raise ValueError(f"Bitwarden readback mismatch for {name}")
            item = verified
            created.append(name)
        else:
            raise ValueError(f"missing Bitwarden record for {name}; create gate required for generated keys")
        if not item.value:
            raise ValueError(f"empty Bitwarden value for {name}")
        results[name] = item.value
    return {"values": results, "created": created}


def main():
    request = json.load(sys.stdin)
    from bitwarden_sdk import BitwardenClient  # installed on the controller, never on the host
    token = os.environ.get("BWS_ACCESS_TOKEN")
    if not token:
        raise ValueError("BWS_ACCESS_TOKEN missing on Ansible controller")
    client = BitwardenClient()
    client.auth().login_access_token(token)
    data = resolve(client, UUID(request["project_id"]),
                   UUID(request["organization_id"]), request["keys"],
                   request.get("record_ids", {}), request["create"])
    print(json.dumps(data))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Do not leak SDK exceptions or URLs (which may contain credentials).
        print("Bitwarden resolution failed; inspect access, ids, duplicates or SDK availability", file=sys.stderr)
        sys.exit(1)
