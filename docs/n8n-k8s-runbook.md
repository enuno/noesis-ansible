# n8n deployment runbook

## Source-backed installation options

As of 2026-10-25, the official n8n documentation describes these self-hosting paths:

- Direct Linux setup: `curl -fsSL https://get.n8n.io | sh`. The current docs say this setup requires Docker on Linux or macOS. It is convenient, but it is not the selected production path here.
- Docker: `docker run` with image `docker.n8n.io/n8nio/n8n`, port 5678, and a persistent `/home/node/.n8n` volume. The n8n docs mark the older raw Docker page as outdated and recommend Docker Compose.
- Docker Compose: use the official `n8n-hosting` examples. Compose is the recommended multi-container path and is the correct choice when PostgreSQL and other supporting services are managed on one Linux host.
- Kubernetes: use the official OCI chart `oci://ghcr.io/n8n-io/n8n-helm-chart/n8n`. This deployment pins chart 1.17.0, digest `sha256:87632113aefe2228090da8895ee3bd512a0f658f0c31854a6c66bd8aa65bb379`, and app version 2.44.5.

Sources:

- https://docs.n8n.io/hosting/installation/
- https://docs.n8n.io/hosting/installation/docker/
- https://github.com/n8n-io/n8n-hosting
- https://github.com/n8n-io/n8n-hosting/tree/main/charts/n8n
- https://tailscale.com/docs/kubernetes-operator/ingress
- https://tailscale.com/docs/kubernetes-operator/connector

## Selected Kubernetes design

The chart runs standalone mode with SQLite on the existing k3s local-path PVC. It uses the external task-runner sidecar, a ClusterIP Service, and the existing Tailscale Kubernetes Operator.

The chart creates a standard `networking.k8s.io/v1` Ingress with class `tailscale`. The operator creates the per-service Tailscale proxy instance and assigns `n8n.tailf99a0.ts.net`. The Kubernetes Service remains private.

A Tailscale `Connector` is not used for HTTP ingress. Tailscale documents Connector as a subnet-router/exit-node resource that advertises CIDR routes. Enabling it for this service would advertise a broader network than necessary. The role keeps Connector creation as an explicit opt-in only when a future approved CIDR-routing requirement exists.

## Secrets

Bitwarden project: `72974d0e-81af-4678-bab7-b46000985859` (`noosphere`). The deployment reads these records and delivers them to a Kubernetes Secret named `n8n-secrets`:

- `N8N_K3S_DEFAULT_ENCRYPTION_KEY`
- `N8N_K3S_DEFAULT_RUNNERS_AUTH_TOKEN`

Values are never committed. The playbook requires both records to exist before Helm installation.

## Deploy

```bash
cd ~/projects/noesis-ansible
ANSIBLE_VAULT_PASSWORD_FILE=/path/to/vault-password \
ansible-playbook -i inventory/n8n-k8s/hosts.ini playbooks/n8n-k8s.yml
```

The controller must provide `BWS_ACCESS_TOKEN` through the approved credential mechanism. The current target account does not inherit Elvis's interactive shell environment, so pass it through a protected temporary extra-vars file or provision the approved non-interactive credential for `ansible`.

## Verification

```bash
kubectl -n n8n get deploy,pod,svc,pvc,ingress
helm status n8n -n n8n
kubectl -n n8n get ingress n8n-main -o wide
```

Expected live state from the completed Helm installation:

- Helm release `n8n` is `deployed`.
- Deployment `n8n-main` is `1/1` available.
- Pod has `2/2` containers ready: n8n and task-runner.
- PVC `n8n` is `Bound` with `10Gi` on `local-path`.
- Ingress is class `tailscale` and reports `n8n.tailf99a0.ts.net`.

## Tailnet Lock prerequisite

The generated proxy currently cannot serve traffic until its node is signed by a trusted Tailnet Lock signing device. The live proxy reported:

`this node is locked out; it will not have connectivity until it is signed`

The node key is shown only in the operator diagnostics. A tailnet administrator must sign that exact pending n8n node from a trusted signing device. This is an external Tailscale control-plane action; the Helm release and Kubernetes resources are already deployed.
