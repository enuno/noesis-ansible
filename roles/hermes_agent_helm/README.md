# hermes_agent_helm

Reusable target-side deployment role for the **jyje community `hermes-agent`
Helm chart** (vendored chart `1.21.0`, app `v0.22.2`). It deploys a separate
minimal Hermes instance with no NoesisPraxis identity or memory imports.

Evidence: `docs/praxis-k3s/pins.md` (pins/integrity) and
`docs/praxis-k3s/hermes-chart.md` (values/security/PVC behavior).

## Execution model and requirements

The role runs under `hosts: k3s_server`, `become: true`. Kubernetes and Helm
modules execute on the target and use `/etc/rancher/k3s/k3s.yaml` **in place**;
cluster-admin credentials are never copied to the controller.

- Target-side `/usr/local/bin/helm` (installed by reusable `roles/helm`).
- Target-side Python Kubernetes client (the playbooks pin `kubernetes==34.1.0`
  in `/opt/ansible-kubernetes`).
- Controller collection `kubernetes.core >=5.0.0`.
- Vendored chart source on controller; the role copies it to
  `/opt/hermes-agent-chart` on the target before invoking Helm.

## Required vault-injected variables

| Variable | Purpose |
|---|---|
| `hermes_agent_dashboard_password` | Dashboard basic-auth password (>=16 chars). |
| `hermes_agent_provider_env` | Non-empty provider credential map, e.g. `{"OPENAI_API_KEY":"..."}`. |

## Enforced behavior

- Release `hermes-agent`, namespace `hermes-agent`, idempotent
  `upgrade --install`; role never uninstalls.
- Atomic, bounded Helm operation (default 300 seconds): failed installs are
  removed; failed upgrades roll back to the previous release.
- One replica, Recreate strategy (chart-forced with persistence).
- `/opt/data` on a 5Gi `local-path` RWO PVC; role never deletes PVCs.
- Externally managed provider/dashboard Secret (`no_log`, no diff) injected
  via `extraEnvFrom`; chart-managed placeholder env is overridden to `{}`.
- ClusterIP dashboard only; no Ingress/NodePort/LoadBalancer.
- Hardened uid/gid 10000 security contexts, read-only rootfs, dropped
  capabilities, RuntimeDefault seccomp, bounded writable `/run` and `/tmp`.
- Deny-all-ingress NetworkPolicy is rendered, but k3s flannel does not enforce
  NetworkPolicy without an additional policy engine.

## PVC retention

The chart-created PVC is deleted by `helm uninstall`; this role never
uninstalls. For retention independent of Helm, pre-create a claim and set
`hermes_agent_persistence_existing_claim`.

## Usage

```bash
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/hermes-deploy.yml \
  -e @group_vars/secrets.yml --vault-password-file .vault_pass
```
