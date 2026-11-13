# Vendored Radar Helm chart

| Field | Value |
| --- | --- |
| Upstream chart | `skyhook/radar` from `https://skyhook-io.github.io/helm-charts` |
| Also published | `oci://ghcr.io/skyhook-io/charts/radar` |
| Chart version | `1.20.2` |
| App version | `1.20.2` |
| Image | `ghcr.io/skyhook-io/radar:1.20.2` |
| Source repo | https://github.com/skyhook-io/radar |
| Package sha256 | `5a76a6b7c60cc7c5cee625ea667b8f7ad0272920bdf0ce19d6fe201a9bb18087` |
| Image digest | `sha256:68fe38aeb010a0a4b5110667a03a97b2e03f045559acdc31721a1f6c529f6cb7` |
| Vendored | 2026-11-09 |

This directory is an unmodified unpack of the published chart tarball
(`helm pull skyhook/radar --version 1.20.2`). Do not edit templates in place.
To bump: pull the new version, replace this tree, update package sha256, and
bump `radar_k8s_chart_version` / image tag in `roles/radar_k8s/defaults/main.yml`
together.

Canonical upstream path in the Radar monorepo is `deploy/helm/radar` (synced
to `skyhook-io/helm-charts` on release). This vendor copy is the published
artifact, not a git checkout of `main`.
