# Provenance

This chart is maintained by Noesis and is not an official OpenClaw Helm chart.

Inspected upstream release: `openclaw/openclaw` tag `v2026.10.5` (release
published 2026-10-18T21:47:25Z). The Kubernetes source tree was inspected at
`scripts/k8s/manifests` on 2026-10-20. Relevant Git blob revisions:

- `configmap.yaml`: `552dc6f9d95e4cf6c0005da1b6bc20e77459a50c`
- `deployment.yaml`: `d7d3e359642ebbd03da573392e3808898bd56fc3`
- `pvc.yaml`: `e834e788a0e4b591a9b704037f31083d36a7f7de`
- `service.yaml`: `41df62197826b949c7d3d0ace8d75d49c5ec31f3`

The chart preserves upstream seed-if-missing semantics, UID/GID 1000,
read-only root filesystem, dropped capabilities, 10Gi PVC default, port 18789,
and JSON-contract exec probes. The release image was independently queried from
GHCR on 2026-10-20 and pinned to OCI index digest
`sha256:f40d1e66fd14d8c5b49c832f4100f83b53fdc01f5108f7db11de38fd0ee6dbe5`.
