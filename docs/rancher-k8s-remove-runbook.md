# Rancher full removal runbook (k3s)

## Purpose

Completely remove Rancher Manager and the components it installed on the local
k3s cluster so Radar (or nothing) owns the UI surface.

## What is removed

Helm releases (order enforced by the role):

| Namespace | Release |
| --- | --- |
| cattle-system | rancher |
| cattle-system | rancher-webhook |
| cattle-system | system-upgrade-controller |
| cattle-turtles-system | rancher-turtles |
| cattle-fleet-local-system | fleet-agent-local |
| cattle-fleet-system | fleet |
| cattle-fleet-system | fleet-crd |

Also:

- Tailscale Ingress `rancher` in `cattle-system`
- Namespaces matching `cattle-*`, `fleet-*`, `cluster-fleet-*`, `p-*`,
  `user-*`, plus known exact names (`local`, `fleet-default`, …)
# CRDs whose names contain `.cattle.io`, `cluster.x-k8s.io`, or `turtles-`
  (excluding `*.k3s.cattle.io` and k3s HelmChart CRDs)

## What is never touched

`default`, `kube-system`, `kube-public`, `kube-node-lease`, `tailscale`,
`radar`, `mcpjungle`, `n8n`, `unifi-mcp`, `buzz`, `hermes-agent`, `openclaw`,
`mcp-gateway`, and other app namespaces on the deny list.

## Gate

Default `rancher_k8s_remove_enabled: false`. Authorized run:

```bash
cd ~/projects/noesis-ansible
printf '[defaults]\nroles_path=%s/roles\n' "$PWD" > /tmp/nocfg.ini

ANSIBLE_CONFIG=/tmp/nocfg.ini ansible-playbook \
  -i inventory/rancher-k8s/hosts.ini \
  playbooks/rancher-k8s-remove.yml \
  -e rancher_k8s_remove_enabled=true
```

## Verify

```bash
helm list -A | rg -i 'rancher|fleet|turtles|system-upgrade'   # expect empty
kubectl get ns | rg -i 'cattle|fleet|local'                     # expect empty or Terminating
kubectl get crd | rg -i 'cattle\.io'                            # expect empty
```

## Notes

- This is destructive and irreversible for Rancher local-cluster state.
- Bitwarden records `rancher_k3s_bootstrap_password` /
  `rancher_k3s_admin_password` are **not** deleted (durable escrow remains).
- system-upgrade-controller was installed by Rancher on this cluster; removal
  is intentional. Re-add a first-party k3s upgrade path separately if needed.
