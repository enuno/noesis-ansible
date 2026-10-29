#!/usr/bin/env python3
"""Resolve the Hermes dashboard credentials from Bitwarden Secrets Manager.

Input JSON on stdin, output JSON on stdout. Secret values never appear in
argv: the access token comes from the environment and every request parameter
travels through stdin. Only invoked by no_log Ansible tasks; do not run from
an interactive terminal.

Request:
  {"project_id": "<uuid>", "organization_id": "<uuid>",
   "keys": {"<logical>": "<BWS_KEY>", ...},
   "record_ids": {"<logical>": "<uuid>", ...}}

Response:
  {"values": {"<logical>": "<value>", ...}}
"""
import json
import os
import sys
from uuid import UUID

from bitwarden_sdk import BitwardenClient  # installed on the controller, never on the host


def resolve(client, project_id, organization_id, keys, record_ids):
    """Project get verifies the machine account can see the intended project."""
    project = client.projects().get(str(project_id)).data
    if UUID(str(project.organization_id)) != organization_id:
        raise ValueError("project does not belong to the configured organization")

    listed = client.secrets().list(str(organization_id)).data.data
    results = {}
    for logical, key in keys.items():
        matches = [entry for entry in listed if entry.key == key
                   and project_id in [UUID(str(p)) for p in entry.project_ids]]
        pinned = record_ids.get(logical)
        if pinned:
            matches = [entry for entry in matches if str(entry.id) == str(UUID(pinned))]
            if len(matches) != 1:
                raise ValueError(f"pinned record missing for {logical}")
        elif len(matches) != 1:
            raise ValueError(f"ambiguous or missing Bitwarden key for {logical}; pin an id")
        item = client.secrets().get(str(matches[0].id)).data
        if key != item.key or project_id != UUID(str(item.project_id)):
            raise ValueError(f"record for {logical} is not in the expected project")
        if not item.value:
            raise ValueError(f"empty Bitwarden value for {logical}")
        results[logical] = item.value
    return results


def main():
    request = json.load(sys.stdin)
    token = os.environ.get("BWS_ACCESS_TOKEN")
    if not token:
        raise ValueError("BWS_ACCESS_TOKEN missing on Ansible controller")
    client = BitwardenClient()
    client.auth().login_access_token(token)
    values = resolve(client,
                     UUID(request["project_id"]),
                     UUID(request["organization_id"]),
                     request["keys"],
                     request.get("record_ids", {}))
    print(json.dumps({"values": values}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Do not leak SDK exceptions or URLs (which may contain credentials).
        print("Bitwarden resolution failed; inspect access, ids, duplicates or SDK availability",
              file=sys.stderr)
        sys.exit(1)
