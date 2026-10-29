#!/usr/bin/env python3
"""Create/refresh the Hermes dashboard credential records in Bitwarden SM.

Secret values never appear in argv: every input is read from the environment
and output is limited to ids/keys/lengths/hashes.

Environment:
  BWS_ACCESS_TOKEN      (required) Bitwarden SM access token
  BWS_PROJECT_ID        (required) target project UUID
  BWS_ORG_ID            (required) organization UUID
  BWS_SOURCE_PW_ID      (required) existing password record UUID to promote
                        (so no credential is rotated as a side effect)
  BWS_DASHBOARD_USER    (optional) dashboard username, default hermes-admin

Creates/updates, in BWS_PROJECT_ID:
  HERMES_K3S_DASHBOARD_USERNAME
  HERMES_K3S_DASHBOARD_PASSWORD
  HERMES_K3S_DASHBOARD_SESSION_SECRET
"""
import base64
import hashlib
import os
import secrets
import sys
import uuid

from bitwarden_sdk import BitwardenClient

PROJECT_KEYS = {
    "username": "HERMES_K3S_DASHBOARD_USERNAME",
    "password": "HERMES_K3S_DASHBOARD_PASSWORD",
    "session_secret": "HERMES_K3S_DASHBOARD_SESSION_SECRET",
}

NOTE = ("Hermes web UI dashboard credential for the k3s noesis-praxis "
        "deployment (https://noesis-praxis.tailf99a0.ts.net/).")


def env_uuid(name):
    raw = os.environ.get(name, "").strip()
    if not raw:
        raise SystemExit(f"{name} missing")
    return uuid.UUID(raw)


def main():
    project_id = env_uuid("BWS_PROJECT_ID")
    org_id = env_uuid("BWS_ORG_ID")
    source_pw_id = env_uuid("BWS_SOURCE_PW_ID")
    username = os.environ.get("BWS_DASHBOARD_USER", "hermes-admin").strip() or "hermes-admin"

    token = os.environ.get("BWS_ACCESS_TOKEN", "").strip()
    if not token:
        raise SystemExit("BWS_ACCESS_TOKEN missing")

    c = BitwardenClient()
    c.auth().login_access_token(token)

    listed = c.secrets().list(org_id).data.data

    source = c.secrets().get(str(source_pw_id)).data
    if not source.value:
        raise SystemExit("source password record has an empty value")

    desired = {
        PROJECT_KEYS["username"]: username,
        PROJECT_KEYS["password"]: source.value,
        PROJECT_KEYS["session_secret"]: base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
    }

    created = []
    for key, value in desired.items():
        matches = [e for e in listed if e.key == key
                   and project_id in [uuid.UUID(str(p)) for p in e.project_ids]]
        if matches:
            item = c.secrets().get(str(matches[0].id)).data
            if item.value != value:
                item = c.secrets().update(str(item.id), value, item.note, item.project_ids).data
                action = "updated"
            else:
                action = "unchanged"
        else:
            item = c.secrets().create(org_id, key, value, NOTE, [project_id]).data
            created.append(key)
            action = "created"
        verified = c.secrets().get(str(item.id)).data
        if verified.key != key or verified.value != value:
            raise SystemExit(f"readback mismatch for {key}")
        print(f"  {action:9s} {key} id={verified.id} len={len(value)} "
              f"sha={hashlib.sha256(value.encode()).hexdigest()[:12]}")
    print("created:", ",".join(created) if created else "(none)")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        print("Bitwarden write failed; inspect access, ids, duplicates or SDK availability",
              file=sys.stderr)
        sys.exit(1)
