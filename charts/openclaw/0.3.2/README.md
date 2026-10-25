# OpenClaw Helm chart 0.3.2

Noesis-maintained packaging; this is **not** an official OpenClaw chart. Upstream
ships Kubernetes manifests under `scripts/k8s`, not Helm packaging.

The chart is intentionally single-writer: one replica, `Recreate`, one PVC, no
HPA, a ClusterIP Service, no RBAC, and service-account token automount disabled.
It never creates a Secret. Set `existingSecret` to a pre-existing Secret that
contains `OPENCLAW_GATEWAY_TOKEN` and any optional provider API keys.

`openclaw.json` and `workspace/AGENTS.md` are copied from the ConfigMap only when
missing. After first boot the PVC copies are authoritative. Back them up and edit
or deliberately remove them before expecting changed seed data to apply.

The NetworkPolicy defaults to no ingress, allows ingress from the configured
Tailscale operator namespace only when Ingress is enabled, and allows DNS plus
TCP/443 egress. Enforcement depends on a NetworkPolicy-capable CNI; k3s
`local-path` storage and the default flannel configuration do not by themselves
provide policy enforcement or replicated storage.
