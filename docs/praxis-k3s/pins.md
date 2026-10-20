# Praxis K3s — Dependency Pins

Pinned, verified upstream artifacts for the minimal single-node k3s Hermes
Agent deployment (target design host: `31.97.209.57`, Ubuntu 26.04 x86_64,
single-node k3s, `local-path` StorageClass, Traefik + servicelb disabled).

## hermes-agent Helm chart (jyje community chart)

| Field | Value |
|-------|-------|
| Chart name | `hermes-agent` |
| Chart repository (Helm HTTP) | `https://jyje.github.io/hermes-agent-helm` |
| Chart repo add | `helm repo add hermes-agent https://jyje.github.io/hermes-agent-helm` |
| Pinned chart version | **`1.21.0`** |
| App version (upstream Hermes) | **`v0.22.2`** |
| Chart publish date | 2026-10-17 (per repo `index.yaml`) |
| Upstream maintainer | jyje (jyjeon@outlook.com) |
| Chart license | MIT |
| Chart source | https://github.com/jyje/hermes-agent-helm |
| Application source | https://github.com/NousResearch/hermes-agent |
| Vendor location (this repo) | `charts/vendor/hermes-agent/` |

### Image pin

| Field | Value |
|-------|-------|
| Image reference | `nousresearch/hermes-agent:v0.22.2` |
| Immutable manifest-list digest | `sha256:36099926da316742423544e055d4734777105ffe6341873af5459b957d0c2919` |
| linux/amd64 child digest | `sha256:a11574b7fe8e1631d7d88d556677dac693bc058abf558cdeb899155688c1bf05` |
| linux/arm64 child digest | `sha256:6793b8c89a44872fc9a5ef135ac0c28bf0a7b9caf4968278195b14e43919aef5` |
| Architecture compatibility | ✅ multi-arch manifest list includes **linux/amd64** (target is x86_64) and linux/arm64 |

The chart's `image.repository`/`image.tag` values are the only image keys
(verified against `values.schema.json` — there is **no `image.digest` key**).
Digest enforcement is therefore done at verify time:
`playbooks/hermes-verify.yml` asserts the node's running `imageID` resolves to
the pinned manifest-list digest above.

### Integrity / provenance evidence

1. **Repo index digest match.** The chart repository's `index.yaml` records
   digest `sha256:89383fff8a5728048adeacc3a4d7f13b71593f3b5e87dd6a7c74ed41ca477e2a`
   for `hermes-agent-1.21.0.tgz`. The tarball pulled on 2026-10-18 (controller)
   hashes to exactly that value (`shasum -a 256`):
   `89383fff8a5728048adeacc3a4d7f13b71593f3b5e87dd6a7c74ed41ca477e2a`. ✅ match.
2. **Artifact Hub listing.** `https://artifacthub.io/packages/helm/hermes-agent/hermes-agent`
   shows chart 1.21.0 / app v0.22.2, **verified publisher**, **cosign-signed**
   (`Signature: cosign`), license MIT, container image
   `nousresearch/hermes-agent:v0.22.2`.
3. **Registry-verified image digest.** Digest and platform list resolved live
   from `registry-1.docker.io` (anonymous pull token, `Accept:
   application/vnd.docker.distribution.manifest.list.v2+json`) — not taken
   from documentation.

### Limitations of provenance chain

- **No `.prov` (helm provenance) file**: `helm pull --prov` returns 404 for
  this version on the GitHub Pages repo, so `helm verify` cannot run against
  the HTTP repo. Integrity rests on the index digest match (item 1), TLS, the
  vendored copy, and the registry-verified image digest.
- **OCI/cosign path not anonymously accessible**: Artifact Hub lists
  `oci://ghcr.io/jyje/hermes-agent-helm/hermes-agent` (cosign-signed), but
  anonymous pulls are denied (`403`). Operators with GHCR access may
  additionally run `cosign verify` against that reference; this was not
  possible from the authoring controller.

## Rationale

- **1.21.0** is the latest stable chart version at pin time (2026-10-18);
  1.20.0 (same app version v0.22.2) is the immediate fallback.
- **Deployment controller + forced Recreate**: the chart forces
  `strategy: Recreate` whenever persistence is enabled, which — with
  `replicaCount: 1` and a `ReadWriteOnce` PVC — gives the required
  single-writer semantics without StatefulSet identity overhead.
- **v0.22.2 app**: current upstream; chart README carries upgrade notes for
  the v0.22 line (persisted-session caveat for v0.22.1 migrations; not
  applicable to this greenfield deployment).
- This Hermes instance is a **separate minimal deployment**: it does not
  claim the NoesisPraxis identity, clone memories, or copy any existing
  profile. Values/templates in `roles/hermes_agent_helm/` carry no Noesis
  branding or memory imports.

## Execution model addendum

Hermes deploy and verification run **on `k3s_server` with sudo**, not on the
Ansible controller. `kubernetes.core` modules read
`/etc/rancher/k3s/k3s.yaml` in place on the target, so cluster-admin
credentials never leave the host. The vendored chart is copied to
`/opt/hermes-agent-chart` and Helm consumes that target-side path.

Target dependencies are explicit and pinned where upstream artifacts matter:

| Dependency | Pin / installation |
|---|---|
| Helm CLI | **`v4.3.1`**, Linux amd64 tarball SHA-256 `0403a88ae20913d11b10a2467b50087721fea7581736da6b9d3992f5357fe54b`; release discovered from GitHub releases API, checksum from the official get.helm.sh `.sha256sum`; installed by `roles/helm` to `/usr/local/bin` |
| Python Kubernetes client | **`kubernetes==34.1.0`** in target venv `/opt/ansible-kubernetes`; exact pip pin avoids Ubuntu system-Python mutation and unpinned distro drift |
| Kubeconfig | `/etc/rancher/k3s/k3s.yaml`, target-local root-only file; never copied |

Helm operations are atomic and bounded to 300 seconds by default: failed new
installs are removed and failed upgrades roll back to the prior successful
release. This does not authorize or perform an uninstall, and the playbooks
never delete the PVC.

## Tailscale package policy

`playbooks/tailscale-install.yml` deliberately passes `state: present` to the
existing `roles/tailscale`. On Ubuntu this role installs the `tailscale`
package from Tailscale's official stable apt repository but exposes no separate
exact-version variable; its package name is fixed and its only states are
`present`, `latest`, and `absent`. An invasive role fork or fabricated numeric
version is therefore not justified.

The conservative policy is: install the repository-current package only when
Tailscale is absent, and never auto-upgrade it on an unchanged rerun. Exact
numeric apt pinning is deferred until approved preflight can read the target's
official apt repository metadata. During that live preflight/verification,
record `tailscale version` and `apt-cache policy tailscale`; then review and
document an exact supported version before adding pin support.

Live record (2026-10-19, noesis-praxis first install): `tailscale version`
1.104.1 (commit 7f4efe814ff14b064eb080344389ceb9ea2d37ac); `apt-cache policy
tailscale` Installed 1.104.1, Candidate 1.104.1. tailscaled enabled+active,
not enrolled (enrollment gate held pending auth key). Exact apt pinning
remains a deliberate follow-up; no auto-upgrade on rerun.
