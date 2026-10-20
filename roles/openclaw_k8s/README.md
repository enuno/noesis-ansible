# openclaw_k8s

Deploys the repository-maintained OpenClaw chart with an immutable image digest.
It mirrors the Buzz execution model: chart and rendered non-secret values are
staged on the managed kubeconfig host; every Kubernetes module receives explicit
`kubeconfig` and `context` values.

Defaults fail closed: missing context, Secret, storage, or exposure inputs fail;
Service type is always ClusterIP; Tailscale Ingress is opt-in; token auth remains
enabled; one replica uses Recreate; no HPA or RBAC is created.

Use the lifecycle playbooks and `docs/openclaw-k8s.md`. Do not invoke task files
directly. Removal retains the PVC unless both the destructive flag and exact
confirmation string are supplied.
