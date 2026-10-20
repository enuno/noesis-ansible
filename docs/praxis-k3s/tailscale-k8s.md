# Tailscale in-cluster (operator pivot, 2026-10-19)

## Decision

Per operator directive, the `noesis-praxis` tailnet identity moved **into the
k3s cluster** via Tailscale's official Helm chart. The host apt `tailscaled`
is purged by the migration. This supersedes the host-package + Serve design
documented in `tailscale-serve.md` (retained for rollback reference).

## What runs where

| Component | Location | Notes |
|---|---|---|
| `tailscale-operator` Deployment + CRDs | ns `tailscale` | vendored chart `charts/vendor/tailscale-operator` 1.104.1 (app v1.104.1) |
| OAuth Secret `tailscale-operator-oauth` | ns `tailscale` | from vault keys `tailscale_k8s_oauth_client_id/secret`; mounted via `oauthSecretVolume` — never via helm values |
| Dashboard Ingress `noesis-praxis` | ns `hermes-agent`, class `tailscale` | operator provisions a proxy pod that joins the tailnet as `noesis-praxis.tailf99a0.ts.net` with managed TLS |
| Host `tailscaled` | **removed** | logout → disable/stop → apt purge (role action `remove-host`) |
| Hermes NetworkPolicy | ns `hermes-agent` | two rules: node `/32` (legacy, inert) + `namespaceSelector: tailscale` (live path) |
| Hermes `trustedProxies` | app config | `31.97.209.57/32`, `10.42.0.1/32`, `10.42.0.0/24` (proxy pod source — pending empirical confirmation) |

## Operator prerequisites (one-time, in the Tailscale admin console)

1. OAuth client: <https://login.tailscale.com/admin/settings/oauth> —
   scopes `devices:core`, `devices:write`; suggested tags `tag:k8s-operator`.
   **The client secret is shown once**; store both values in the encrypted
   vault under `tailscale_k8s_oauth_client_id` / `tailscale_k8s_oauth_client_secret`.
2. ACLs: `tagOwners` allowing `tag:k8s-operator` to own `tag:k8s` (see
   `roles/tailscale_k8s/README.md` for the JSON snippet).

BSM currently holds `TAILSCALE_CLIENT_ID` only — no client secret exists in
any of the three BSM projects (verified 2026-10-19). The OAuth client secret
is the one hard blocker for the migration.

## Run

```sh
ANSIBLE_VAULT_PASSWORD_FILE=... ansible-playbook \
  -i inventory/praxis-k3s/hosts.ini \
  playbooks/tailscale-k8s-migrate.yml -f 1 -e @<encrypted-vault>.yml
ANSIBLE_VAULT_PASSWORD_FILE=... ansible-playbook \
  -i inventory/praxis-k3s/hosts.ini \
  playbooks/tailscale-k8s-verify.yml -f 1 -e @<encrypted-vault>.yml
```

Brief dashboard outage occurs between the `remove-host` and `expose` phases.

## Rollback

Manual: reinstall host tailscale (`playbooks/tailscale-install.yml`,
kept/deprecated for this), delete the dashboard Ingress, re-apply
`tailscale-serve.yml`. The operator itself can remain installed harmlessly
(until a full teardown is desired).

## First-live-run verification checklist (SSH was down at authoring time)

- [ ] Operator Deployment ready; CRDs `proxyclasses/connectors.tailscale.com` established
- [ ] Ingress assigned `noesis-praxis.tailf99a0.ts.net`; proxy pod Running
- [ ] Proxy pod label selector guess (`tailscale.com/proxy-for`) correct — adjust if the wait misbehaves
- [ ] Dashboard-observed source IP ∈ `10.42.0.0/24` (else fix `trustedProxies`)
- [ ] `tailscale-k8s-verify.yml` green incl. 401 contract on `/api/sessions`
- [ ] `hermes-verify.yml` green with the two-rule NetworkPolicy assertion
- [ ] Idempotence: migrate rerun → `changed=0`
