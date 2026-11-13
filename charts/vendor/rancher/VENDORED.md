# Vendored Rancher chart — provenance and deviation

## Source

- Repository: `https://releases.rancher.com/server-charts/stable` (`rancher-stable/rancher`)
- Chart version: `2.15.3` (appVersion `v2.15.3`)
- Upstream package SHA-256: `343888c66421a9f5666b562cdfeca751d63da994edbe7b1b36752f8ffcf5ecd4` (`rancher-2.15.3.tgz`)
- Vendored on: 2026-10-30

## Deviation from upstream (exactly one line)

`Chart.yaml`:

```diff
-kubeVersion: < 1.37.0-0
+kubeVersion: < 1.38.0-0
```

Verified by `diff -r` against the unpacked upstream tarball at vendor time:
this single line is the only difference in the entire tree.

## Why

The deployment target runs k3s `v1.37.1+k3s1`. Every chart published to
rancher-stable (and rancher-latest) at vendor time caps `kubeVersion` below
the target: 2.15.x `< 1.37.0-0`, 2.14.x `< 1.36.0-0`, 2.13.x `< 1.35.0-0`.
Helm hard-fails install/upgrade on a kubeVersion mismatch and offers no
override flag, so no unmodified upstream chart can install on this cluster.
The SUSE support matrix for Rancher 2.15.2 certifies k3s/RKE2 1.34–1.36.

**Consequence: Rancher 2.15.3 on Kubernetes v1.37 is an
unsupported-by-upstream combination.** Approved by the operator on
2026-10-30 with that risk recorded. Rollback: `helm uninstall rancher -n
cattle-system` plus namespace cleanup (see docs/rancher-k8s-runbook.md).

When upstream publishes a chart certifying Kubernetes 1.37, replace this
vendored copy with the official repo chart and update
`roles/rancher_k8s/defaults/main.yml` (`rancher_k8s_chart_ref`) accordingly.
