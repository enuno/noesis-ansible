# Buzz chart provenance

This directory is a vendored copy of the official upstream chart. It is not a
community chart and not a handwritten manifest set.

| Field | Value |
| --- | --- |
| Upstream repository | https://github.com/block/buzz |
| Chart path | deploy/charts/buzz |
| Git revision | 30ca980b49a7479dd89cb1ced0871af05ff1e12e |
| Chart.yaml name | buzz |
| Chart.yaml version | 0.1.11 |
| Chart.yaml appVersion | 0.1.0 |
| Chart.lock digest | sha256:9c0df32008f782064104ecec8552f348841f120852d49ace66966a56ba904348 |
| Chart.lock generated | 2026-06-11T15:45:41.764379-04:00 |
| Chart.yaml sha256 | be33d35ab5d173627a4ba57e3d40e37f1fe83d7fcb7b691aff28bcfa9ddcb3a6 |
| Chart.lock sha256 | dfd65d937800b91a7334412d51da9efbe4525e37ff1981958d507ae0b63d4ae2 |
| values.yaml sha256 | cfa0facc855d25d0bd2608dc8a0d91d2edd021551af0ce6be3e4efb6dc1706c2 |
| values.schema.json sha256 | 1f70b0291b47b634fd620767f1a800b48a975db8b03f86cb3115f3dc5b7ad4af |

## Distribution

Published chart distribution, recorded in the research artifact
`workspace/orchestrator/buzz-ansible-20261018/UPSTREAM-EVIDENCE.md`, is OCI
`oci://ghcr.io/block/buzz/charts/buzz` with live tag `0.1.11`. This role does
not pull that registry at apply time.

This directory is an unpacked vendored tree from git revision
`30ca980b49a7479dd89cb1ced0871af05ff1e12e` (`main` at the time of packaging).
That is not the `chart-v0.1.11` tag commit `5a93e862ee28b8804f681ae15997a00bdc45d1bf`.
Research reported Chart.yaml, Chart.lock, values, and templates identical
between those two commits, with a README-only difference. This role did not
re-package the OCI layer, so the vendored tree is not claimed to be
byte-identical to the published OCI chart.

## Dependencies

Resolved from `Chart.lock` without changing versions. `helm dependency build`
on Helm v4.3.1 exited 1 with Docker Hub 401 before writing these tarballs.
The same lock coordinates were then fetched from the anonymous registry API
and checked against the returned OCI layer digests. `Chart.lock` was not
rewritten. `helm dependency list` then reported both dependencies `ok`.

| Chart.lock name | Version | Repository | OCI reference | Manifest digest | Layer sha256 |
| --- | --- | --- | --- | --- | --- |
| postgres | 0.19.5 | oci://registry-1.docker.io/cloudpirates | oci://registry-1.docker.io/cloudpirates/postgres:0.19.5 | sha256:41a9f2b51c39d69590515ff04056f023634cafa55464eeba209664efecede454 | sha256:3dfab3d33c3c4cd311201eee4dc350c2386f3b42152df984f87b499d71bf62a2 |
| redis | 0.30.3 | oci://registry-1.docker.io/cloudpirates | oci://registry-1.docker.io/cloudpirates/redis:0.30.3 | sha256:bc8d239479a5b1c82ef454c02e641e9fa810c764667a4c9bbd67b77a4940e880 | sha256:da82f755fc32348755a2b49adc29a0caca4c1b89abd90067073a9835dae98534 |

Packaged files:

- `charts/postgres-0.19.5.tgz`
- `charts/redis-0.30.3.tgz`

Do not run `helm dependency update` in this directory. That rewrites
`Chart.lock` and can change versions.
