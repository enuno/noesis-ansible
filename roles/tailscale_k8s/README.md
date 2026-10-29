# tailscale_k8s

Deploys the **official Tailscale Kubernetes Operator** (vendored Helm chart,
`charts/vendor/tailscale-operator`, chart 1.104.1 / app v1.104.1) into the
k3s cluster and exposes the Hermes dashboard tailnet-only through a
`tailscale` Ingress — replacing the host-level `tailscaled` + Serve design.

## Architecture after migration

```
tailnet client ──(WireGuard, tailnet-only)──> operator proxy pod (ns tailscale)
                                                    │ pod-to-pod, ClusterIP
                                                    ▼
                                          hermes-agent:9119 (ClusterIP, NP-gated)
```

- The operator-managed proxy enrolls as `noesis-praxis.tailf99a0.ts.net`
  with operator-provisioned TLS. Funnel is never enabled.
- The host `tailscaled` package is purged; nothing host-side remains on the
  tailnet. **Never run host tailscaled and this role concurrently** — two
  tailscaled instances must not share one identity.
- The Hermes NetworkPolicy admits the node /32 (legacy, inert after
  migration) plus pods in the `tailscale` namespace; the app-level
  `trustedProxies` cover the node pod CIDR (`10.42.0.0/24`) because the
  dashboard observes the proxy pod IP, not the node IP.

## Prerequisites (operator-provisioned, cannot be automated from here)

1. **OAuth client** in the Tailscale admin console
   (<https://login.tailscale.com/admin/settings/oauth>): scopes
   `devices:core` and `devices:write`; suggested tags `tag:k8s-operator`.
   Client secrets are shown **once** at creation.
2. ACL `tagOwners` allowing `tag:k8s-operator` to own `tag:k8s`:
   ```json
   {"tagOwners": {"tag:k8s-operator": []}, "acls": [{"action": "accept", "src": ["tag:k8s-operator"], "dst": ["*:*"]}]}
   ```
3. Vault file keys `tailscale_k8s_oauth_client_id` /
   `tailscale_k8s_oauth_client_secret` (encrypted vault only — the chart has
   no authKey deployment path).

## Actions

- `install` — stage vendored chart, create ns + OAuth Secret, helm install,
  wait for operator readiness and CRDs.
- `remove-host` — logout/disable/purge host tailscaled.
- `expose` — apply the dashboard Ingress, wait for MagicDNS assignment.
- `dns` — deploy the operator DNSConfig, wire the k3s CoreDNS `ts.net` stub,
  and annotate Tailscale Ingresses for in-cluster MagicDNS resolution.
- `validate` — read-only post-conditions.

## Uncertainties to confirm on first live run (SSH was down at authoring time)

- Proxy pod label key used in the expose wait (`tailscale.com/proxy-for`).
  The authoritative gate is the Ingress hostname assignment; if the label
  guess is wrong the pod-wait times out while the hostname wait still
  validates — adjust the selector empirically.
- The dashboard-observed source IP is expected to be the proxy pod IP
  (`10.42.0.0/24`). Confirm via pod logs and tighten/relax
  `hermes_agent_dashboard_trusted_proxies` if the operator preserves a
  different source.

## Migration

Run `playbooks/tailscale-k8s-migrate.yml`, then
`playbooks/tailscale-k8s-verify.yml`. Expected brief dashboard outage
between the `remove-host` and `expose` phases (the old host Serve path dies
with host tailscaled). Rollback is manual: reinstall host tailscaled
(`playbooks/tailscale-install.yml` — kept for that purpose), delete the
Ingress, re-apply Serve.
