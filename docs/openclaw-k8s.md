# OpenClaw on Kubernetes

Noesis-maintained Ansible and Helm automation for OpenClaw. The chart is not an
official OpenClaw chart; upstream publishes kustomize manifests under
`openclaw/openclaw/scripts/k8s`.

## Architecture and boundaries

One `Recreate` Deployment replica mounts one PVC at `/home/node/.openclaw` and
serves a ClusterIP on TCP 18789. A ConfigMap seeds `openclaw.json` and
`workspace/AGENTS.md` only when each file is absent; after first boot the PVC
copy is authoritative. The ServiceAccount has token automount disabled and no
RBAC objects. The root filesystem is read-only, UID/GID are 1000, capabilities
are dropped, and `XDG_CACHE_HOME=/home/node/.openclaw/.cache` is writable on the
PVC. There is no HPA because the state is single-writer.

Worker identity and broker fields are inert strings or references to a
pre-existing Secret. They do not register workers or confer supervisory,
cluster, or infrastructure authority. The external Noesis dry-run, blast-radius,
and per-action approval contract remains mandatory for infra-acting workers.

## Pin table

| Item | Pin |
| --- | --- |
| Chart | Noesis-maintained `0.1.0` |
| Chart appVersion | `2026.10.5` |
| Image tag verified | `2026.10.5` |
| OCI index digest | `sha256:f40d1e66fd14d8c5b49c832f4100f83b53fdc01f5108f7db11de38fd0ee6dbe5` |
| linux/amd64 manifest | `sha256:0be6e07c5c99cdd4466dc9186dc89ebbf68ca8e045c44b4cc496c441a9af1a9e` |
| linux/arm64 manifest | `sha256:31a4b7eb2bb9574527a1e46b2208e1b653f060753dd36fe3da444f79a7d03f0c` |
| Kubernetes Python client | `34.1.0` in `/opt/ansible-kubernetes` |
| kubernetes.core | `>=6.6.0` |

Registry verification was performed 2026-10-20 through the anonymous GHCR token
flow. Query shape:

```bash
TOKEN=$(curl -fsSL 'https://ghcr.io/token?service=ghcr.io&scope=repository:openclaw/openclaw:pull' | jq -r .token)
curl -fsSL -H "Authorization: Bearer $TOKEN" https://ghcr.io/v2/openclaw/openclaw/tags/list
curl -fsSI -H "Authorization: Bearer $TOKEN" -H 'Accept: application/vnd.oci.image.index.v1+json' https://ghcr.io/v2/openclaw/openclaw/manifests/2026.10.5
```

The paginated tags query (`n=1000`) found `2026.10.5` on page 3 after
checking 2,056 tags. The named manifest request returned the index digest above
and the two Linux platform manifests.

## Variables

| Variable | Default | Notes |
| --- | --- | --- |
| `openclaw_k8s_kubeconfig_path` | `/etc/rancher/k3s/k3s.yaml` | Path on managed host; never file contents. |
| `openclaw_k8s_kube_context` | empty | Required explicit context. |
| `openclaw_k8s_release_name` | `openclaw` | Helm release. |
| `openclaw_k8s_namespace` | `openclaw` | Namespace. |
| `openclaw_k8s_chart_version` | `0.1.0` | Immutable repository chart pin. |
| `openclaw_k8s_image_tag` | `2026.10.5` | Human-readable verified tag. |
| `openclaw_k8s_image_digest` | pinned digest | Workload image uses repository plus digest. |
| `openclaw_k8s_existing_secret` | empty | Required name only. Chart never creates a Secret. |
| `openclaw_k8s_storage_class` | empty | Required unless an existing claim is used. |
| `openclaw_k8s_persistence_size` | `10Gi` | State volume. |
| `openclaw_k8s_persistence_access_mode` | `ReadWriteOnce` | Single-writer default. |
| `openclaw_k8s_exposure_enabled` | `false` | Enables only Tailscale Ingress. |
| `openclaw_k8s_ingress_class_name` | empty | Must be `tailscale` when exposed. |
| `openclaw_k8s_tailnet_hostname` | empty | Tailnet hostname placeholder in example. |
| `openclaw_k8s_tailscale_operator_namespace` | `tailscale` | Namespace allowed to reach the pod through the Ingress. |
| `openclaw_k8s_allowed_origins` | `[]` | Must include exact HTTPS tailnet origin when exposed. |
| `openclaw_k8s_gateway_bind` | `loopback` | Must be `lan` only when Ingress is enabled. |
| `openclaw_k8s_gateway_auth_mode` | `token` | Fixed to token auth; Secret supplies token. |
| `openclaw_k8s_worker_identity` | empty | Inert identity string. |
| `openclaw_k8s_broker_endpoint` | empty | Inert endpoint string; no interface is invented. |
| `openclaw_k8s_broker_secret_name/key` | empty | Optional reference pair to a pre-existing Secret key. |
| `openclaw_k8s_live_checks` | `false` | Cluster reads only when true. |
| `openclaw_k8s_destroy_pvc` | `false` | Destructive cleanup gate. |

Replica count, strategy, Service type, port, auth mode, and image pin are
configurable variables but validation intentionally admits only the supported
safe values: 1, Recreate, ClusterIP, 18789, token, and the verified release pin.

## Lifecycle

```bash
ansible-galaxy collection install -r requirements/openclaw.yml
ansible-playbook -i inventory/<real>/hosts.ini playbooks/openclaw-k8s-preflight.yml
ansible-playbook -i inventory/<real>/hosts.ini playbooks/openclaw-k8s-secret.yml
ansible-playbook -i inventory/<real>/hosts.ini playbooks/openclaw-k8s-install.yml
ansible-playbook -i inventory/<real>/hosts.ini playbooks/openclaw-k8s-verify.yml -e openclaw_k8s_live_checks=true
ansible-playbook -i inventory/<real>/hosts.ini playbooks/openclaw-k8s-remove.yml
```

Preflight is read-only and requires the pinned venv to exist. Install and secret
plays create/reuse it using `/usr/bin/python3.14`, then select its Python. Helm
uses atomic wait. A failed upgrade runs an explicit rollback to the prior
revision; a failed first install relies on atomic cleanup.

Removal uninstalls the release but retains the PVC by default. To delete the
chart-created PVC, set both `openclaw_k8s_destroy_pvc=true` and
`openclaw_k8s_destroy_pvc_confirm=DELETE-OPENCLAW-PVC`. Existing claims are never
deleted by this automation.

## Tailscale-only exposure

Exposure requires `openclaw_k8s_exposure_enabled: true`, class `tailscale`,
`gateway.bind: lan`, an exact HTTPS allowed origin, and token authentication.
The Ingress TLS hosts list deliberately has no `secretName`; the Tailscale
operator terminates TLS and creates a separate tailnet device for the Ingress.
The chart does not enable OpenClaw-managed Serve or Funnel and does not mutate
operator installation or tailnet policy.

Revoke access by disabling exposure and reinstalling, then remove or restrict the
corresponding tailnet device/ACL through the separately governed Tailscale
operator process. This automation does not perform that policy change. Tailnet
membership is additive; it never replaces OpenClaw token auth.

OpenClaw keys were verified from the 2026-10-20 docs:
`gateway.bind`, `gateway.auth.mode`, `gateway.controlUi.allowedOrigins`, and
`gateway.trustedProxies`. This chart does not use trusted-proxy auth because the
Tailscale Kubernetes Ingress is TLS transport, not an identity-aware proxy whose
source headers and addresses were verified. Token auth therefore stays enabled.

## Health

Startup and readiness execute `/startupz` and require JSON `ready: true`.
Liveness executes `/healthz` and requires JSON `ok: true`. Monitor `/readyz` and
assert its JSON body; unknown browser paths can return a catch-all 200.

## Persistence, backup, restore, and scheduling

Before every upgrade, rollback, destructive remove, or storage migration, back up
all of `/home/node/.openclaw`, especially `openclaw.json`, `workspace/`, agents,
credentials, session databases, and `.cache` private SQLite snapshots. Also back
up the pre-existing Kubernetes Secret through the operator's approved secret
system. Helm rollback changes manifests only; it does not rewind PVC bytes,
SQLite state, credentials, or seed files.

PVC reclaim behavior is controlled by the StorageClass and PV reclaim policy.
Helm uninstall can delete a chart-created PVC unless it is retained; this chart
adds no promise that the backing PV survives. The Ansible removal path retains
state by default and requires a separate confirmation for PVC deletion.

k3s `local-path` is node-local and suitable only when the pod can return to the
same healthy node. It is not replication. On multi-node clusters use a reviewed
CSI backend that supports the selected access mode, snapshots, restore testing,
and node failure recovery. `ReadWriteOnce` plus Recreate still means one writer;
adding nodes, replicas, or an HPA does not make OpenClaw highly available.

Restore by provisioning a compatible PVC, restoring the directory tree with UID
and GID 1000, restoring the same Secret name, and installing with
`openclaw_k8s_existing_claim` set. Validate `/startupz`, `/healthz`, and
`/readyz` JSON after restore. Do not expect ConfigMap seeds to overwrite restored
files.

## Secret rotation

Rotate values in Bitwarden Secrets Manager, run the secret play, then perform a
reviewed pod restart or Helm upgrade so environment variables are reloaded. Never
place token or provider values in inventory, values files, command output, or Git.
The secret play performs one controller-side `bws secret list`, trims every
value, suppresses all value-bearing output, and applies one Opaque Secret.

## NetworkPolicy limits

The policy defaults to deny ingress and permits only the configured Tailscale
operator namespace when exposure is enabled. Egress permits cluster DNS and
TCP/443 for provider APIs. Enforcement requires a CNI that implements
NetworkPolicy; vanilla k3s flannel may require an additional policy engine.
Namespace labels, DNS pod labels, and operator namespace must match the cluster.
The policy does not install a CNI or any cluster-wide component.

## Local verification ledger

The implementer ran syntax checks, a localhost Jinja/YAML render harness, Helm
lint/template, pytest, and a full-diff secret scan. Exact commands and exit codes
are recorded in `IMPLEMENTER-RESULT-openclaw-k8s.md`. No cluster command, secret
play, install, removal, credential lookup, or tailnet policy action was run.
