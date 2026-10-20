# helm

Reusable role that installs a **pinned, checksum-verified Helm CLI** on the
target host (Ubuntu x86_64). Built for the target-side execution model of the
praxis-k3s playbooks: `kubernetes.core.helm` shells out to the `helm` binary
on the execution host, so under `hosts: k3s_server` the binary must exist on
the target — satisfying the spec requirement *"Install a pinned Helm CLI
where needed for the chosen execution model."*

## Pin

| Field | Value |
|---|---|
| Helm version | **`v4.3.1`** |
| Pin source | `https://api.github.com/repos/helm/helm/releases` — latest stable (non-prerelease, non-draft) at authoring time (published 2026-10-15T01:08:37Z) |
| Artifact | `helm-v4.3.1-linux-amd64.tar.gz` from `https://get.helm.sh` |
| SHA-256 | `0403a88ae20913d11b10a2467b50087721fea7581736da6b9d3992f5357fe54b` (from `get.helm.sh/...tar.gz.sha256sum`, verified at authoring time) |

Bump procedure: query the releases API, update `helm_version`, then fetch the
matching `.sha256sum` from get.helm.sh and update `helm_sha256` — both in
`defaults/main.yml`. Document the change in `docs/praxis-k3s/pins.md`.

## Behavior

- **Idempotent**: runs `helm version --short` first; the download/install
  block is skipped when the installed version equals the pin. Re-runs are
  no-ops.
- **Integrity**: `ansible.builtin.get_url` enforces `sha256:{{ helm_sha256 }}`
  on every download — a tampered or mismatched tarball fails the play.
- **Install target**: `/usr/local/bin/helm` (`0755`, root:root). Requires
  `become` (root).
- **Scratch**: tarball/unpack under `/var/tmp` on the target.

## Requirements

- Target: Ubuntu/Debian x86_64 (playbook asserts this before invoking).
- `become: true` / `sudo`.

## Usage

```yaml
roles:
  - role: helm
```
