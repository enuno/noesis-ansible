# Radar deployment runbook (k3s + Tailscale operator ingress)

## Purpose and architecture

Deploys [skyhook-io/radar](https://github.com/skyhook-io/radar) (open-source
Kubernetes UI + MCP server) onto the single-node k3s cluster with a private,
tailnet-only HTTPS endpoint. There is no public exposure: no NodePort, no
LoadBalancer, no public DNS, no Tailscale Funnel.

Traffic path:

```
authorized tailnet client
  -> https://radar.tailf99a0.ts.net          (MagicDNS, Let's Encrypt cert)
  -> tailscale operator proxy pod ts-radar-* (TLS terminated here)
  -> ClusterIP Service radar:9280 (HTTP)
  -> radar pod
```

- Chart: vendored `skyhook/radar` **1.20.2** at `charts/vendor/radar`
  (see `VENDORED.md`).
- Release: `radar` in namespace `radar`, `replicaCount: 1`.
- Chart Ingress is disabled; the role applies a dedicated
  `networking.k8s.io/v1` Ingress with `ingressClassName: tailscale`, short
  host `radar`, backend `radar:9280`.
- Auth mode defaults to `none`. The **tailnet is the trust boundary**. Anyone
  who can reach the MagicDNS name uses Radar's ServiceAccount grants. Do not
  enable Funnel or a public IngressClass. Enable `auth.mode=proxy|oidc` if
  the audience needs per-user Kubernetes impersonation later.
- Helm write from the UI is off (`rbac.helm: false`). Logs and metrics reads
  stay on.

## Target and execution

Inventory: `inventory/radar-k8s/hosts.ini` — group `radar_k8s`, host
`noesis-lab`, kubeconfig `/etc/rancher/k3s/k3s.yaml`, context `default`.
Durable site values: `inventory/radar-k8s/group_vars/all.yml`.

The repo `ansible.cfg` references a missing `.vault_pass`; this play has no
vault content, so run with a minimal config:

```bash
cd ~/projects/noesis-ansible
printf '[defaults]\nroles_path=%s/roles\n' "$PWD" > /tmp/nocfg.ini

ANSIBLE_CONFIG=/tmp/nocfg.ini ansible-playbook -i inventory/radar-k8s/hosts.ini \
  playbooks/radar-k8s.yml --syntax-check
/usr/bin/python3 tests/radar_k8s/test_offline.py
helm lint charts/vendor/radar

ANSIBLE_CONFIG=/tmp/nocfg.ini ansible-playbook -i inventory/radar-k8s/hosts.ini \
  playbooks/radar-k8s.yml --check

ANSIBLE_CONFIG=/tmp/nocfg.ini ansible-playbook -i inventory/radar-k8s/hosts.ini \
  playbooks/radar-k8s.yml
# idempotency: same command again, expect changed=0
```

## Secrets

Radar with `auth.mode: none` does not require Bitwarden escrow. If a later
revision adds credentials (OIDC client secret, basic-auth htpasswd, etc.),
create them in Bitwarden Secrets Manager project
`72974d0e-81af-4678-bab7-b46000985859` using the key pattern
`SERVICE_NAME_K3S_SECRET_NAME` (example: `RADAR_K3S_OIDC_CLIENT_SECRET`).

## Tailnet Lock

New Tailscale Ingress proxy devices start locked out when Tailnet Lock is on.
After the first deploy, if `https://radar.tailf99a0.ts.net` does not resolve
or connect, check `tailscale lock status` and sign the `radar` node from a
trusted signing device:

```bash
sudo tailscale lock sign nodekey:<from lock status>
```

## Verification

```bash
kubectl -n radar get deploy,pod,svc,endpoints,ingress
helm list -n radar
curl -sS https://radar.tailf99a0.ts.net/api/health
curl -sS -o /dev/null -w '%{http_code}\n' https://radar.tailf99a0.ts.net/
```

## Uninstall

```bash
helm uninstall radar -n radar
kubectl delete ingress radar -n radar --ignore-not-found
kubectl delete namespace radar
```

## Relation to Rancher

Radar replaces Rancher Manager as the cluster UI on this host. Remove Rancher
with `playbooks/rancher-k8s-remove.yml` before or after deploying Radar; the
two do not share a release or namespace.
