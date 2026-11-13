# n8n deployment runbook

## Source-backed installation options

As of 2026-11-12, the official n8n documentation describes these self-hosting paths:

- Direct Linux setup: `curl -fsSL https://get.n8n.io | sh`. The current docs say this setup requires Docker on Linux or macOS. It is convenient, but it is not the selected production path here.
- Docker: `docker run` with image `docker.n8n.io/n8nio/n8n`, port 5678, and a persistent `/home/node/.n8n` volume. The n8n docs mark the older raw Docker page as outdated and recommend Docker Compose.
- Docker Compose: use the official `n8n-hosting` examples. Compose is the recommended multi-container path and is the correct choice when PostgreSQL and other supporting services are managed on one Linux host.
- Kubernetes: use the official OCI chart `oci://ghcr.io/n8n-io/n8n-helm-chart/n8n`. This deployment pins chart 1.19.0, digest `sha256:13b8065b5e3dc657800c300fee36e976f692bb1382930c2ff317944814762943`, and app version 2.47.5.

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

## Version pinning

Chart and application versions are pinned separately, because the chart's `appVersion`
and the n8n release we run are not always the same release:

| Pin | Value | Meaning |
|-----|-------|---------|
| `n8n_k8s_chart_version` | `1.19.0` | Chart release to install |
| `n8n_k8s_chart_digest` | `sha256:13b8065b...` | Immutable OCI artifact for that chart |
| `n8n_k8s_chart_app_version` | `2.47.4` | `appVersion` the chart declares |
| `n8n_k8s_app_version` | `2.47.5` | n8n release this deployment runs |
| `n8n_k8s_image_tag` | `2.47.5` | Image tag rendered into the chart values |
| `n8n_k8s_image_digest` | `sha256:e29e9cc9...` | Multi-arch index digest of `docker.n8n.io/n8nio/n8n:2.47.5` |
| `n8n_k8s_runner_image_digest` | `sha256:1f53745a...` | Multi-arch index digest of `n8nio/runners:2.47.5` |

Chart 1.19.0 declares `appVersion: 2.47.4`, but the chart supports running a
different n8n version: `image.tag` overrides the app version, and the task-runner
tag follows `image.tag` automatically. This deployment runs n8n 2.47.5 (the
current stable release) on chart 1.19.0, so `image.tag` is set explicitly.

Three guards keep this honest:

1. **Digest-pinned chart reference.** The role builds the chart reference as
   `<chart_ref>@<chart_digest>`. Helm rejects the release when the digest does
   not belong to `chart_version`, so a re-pushed upstream tag cannot change
   what is deployed.
2. **Preflight resolves the chart metadata.** Before any cluster change, the
   role runs `helm show chart` against both the plain reference and the
   digest-pinned reference, and asserts the resolved `version` and `appVersion`
   match the pins. The digest check is Helm's own digest/version consistency
   check.
3. **Minor-line coherence.** `n8n_k8s_app_version` and
   `n8n_k8s_chart_app_version` must share the same `major.minor`. A chart that
   jumps minors would otherwise pair with an image it was never built against.

`app.kubernetes.io/version` on the rendered objects reports the chart's
`appVersion` (2.47.4), not the running image tag. The running version is
verified from the pod image IDs instead.

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

The playbook is standalone: it is intentionally not wired into `master-stack.yml`, so it only runs when invoked directly.

### Upgrading a running release

The role upgrades the existing release in place. n8n runs forward-only SQLite
migrations on its PVC, so take a backup before crossing an app version.

Back up the live database with the SQLite online backup API, which produces a
consistent snapshot while the app is still writing:

```bash
PVDIR=$(kubectl -n n8n get pvc n8n -o jsonpath='{.spec.volumeName}' | \
  xargs -I{} kubectl get pv {} -o jsonpath='{.spec.local.path}')
BK=/var/backups/n8n/$(date -u +%Y%m%dT%H%M%SZ)
sudo mkdir -p "$BK"
sudo python3 - "$PVDIR" "$BK" <<'PY'
import sqlite3, sys, os, shutil
src_dir, dst_dir = sys.argv[1], sys.argv[2]
# The SQLite online backup API produces a consistent snapshot even while
# n8n is writing to the WAL. Copying database.sqlite alone would not.
src = sqlite3.connect('file:%s?mode=ro' % os.path.join(src_dir, 'database.sqlite'), uri=True)
dst = sqlite3.connect(os.path.join(dst_dir, 'database.sqlite'))
src.backup(dst)
dst.close(); src.close()
shutil.copy2(os.path.join(src_dir, 'config'), os.path.join(dst_dir, 'config'))
PY
```

Verify the result before relying on it, and record the current migration id so
a rollback target is known:

```bash
sudo python3 -c "
import sqlite3
c = sqlite3.connect('file:$BK/database.sqlite?mode=ro', uri=True)
print('integrity:', c.execute('pragma integrity_check').fetchone()[0])
print('migrations:', c.execute('select max(id) from migrations').fetchone()[0])
"
```

To move to a new n8n release:

1. Update `n8n_k8s_app_version` and `n8n_k8s_image_tag` in `roles/n8n_k8s/defaults/main.yml`.
2. Update `n8n_k8s_image_digest` and `n8n_k8s_runner_image_digest` to the multi-arch index digests of the matching image tags.
3. If the chart also moves, update `n8n_k8s_chart_version`, `n8n_k8s_chart_digest`, and `n8n_k8s_chart_app_version` together, and keep the app version on the same `major.minor` as the chart's `appVersion`.
4. Render and dry-run before applying:

```bash
helm upgrade n8n "oci://ghcr.io/n8n-io/n8n-helm-chart/n8n@<chart_digest>" \
  -n n8n --version=<chart_version> --reuse-values \
  --set image.tag=<app_version> --dry-run=server
```

The role asserts after the rollout that the running pods report the pinned
image digests, so a stale or drifted image fails the run rather than passing
silently.

## self-hosted-ai-starter-kit

Upstream: https://github.com/n8n-io/self-hosted-ai-starter-kit
Vendored from revision `662bd8892476b41d9084417a569cc84013354674`.

Upstream ships the kit as a docker-compose stack (n8n + PostgreSQL + Qdrant +
Ollama + a demo-data import). This deployment renders the equivalent workloads
as **`extraObjects` inside the existing n8n Helm release**, rather than as a
second chart or a parallel Compose stack. One release means one revision
history, one `helm rollback`, and one `helm get manifest` that shows the whole
kit.

| Upstream compose service | Kubernetes object | Default |
|---|---|---|
| `ollama-cpu` / `ollama-gpu*` | Deployment + Service `ollama`, PVC `n8n-starter-kit-ollama` | on, `cpu` profile |
| `qdrant` | Deployment + Service `qdrant`, PVC `n8n-starter-kit-qdrant` | on |
| `postgres` | Deployment + Service `postgres`, PVC `n8n-starter-kit-postgres` | **off** |
| `n8n-import` | Job `n8n-starter-kit-import` (Helm `post-install,post-upgrade` hook) | on |
| `./shared` bind mount | PVC `n8n-starter-kit-shared` mounted at `/data/shared` | on |

Image pins (multi-arch index digests, asserted against the running pods after
rollout):

| Pin | Value |
|---|---|
| `n8n_k8s_starter_kit_ollama_image` | `ollama/ollama:0.40.16` |
| `n8n_k8s_starter_kit_ollama_image_digest` | `sha256:910d0d81...` |
| `n8n_k8s_starter_kit_qdrant_image` | `qdrant/qdrant:v1.20.0` |
| `n8n_k8s_starter_kit_qdrant_image_digest` | `sha256:9bfc89f9...` |
| `n8n_k8s_starter_kit_postgres_image` | `postgres:16-alpine` |
| `n8n_k8s_starter_kit_postgres_image_digest` | `sha256:f377d590...` |

`n8n_k8s_starter_kit_enabled` defaults to **false** in the role and is turned
on in `inventory/n8n-k8s/group_vars/all.yml`. With it off, the role renders
values byte-identical to the pre-kit release; the offline suite asserts that
regression directly.

### Why the demo credentials were re-authored, not copied

Upstream's two credential files carry `data` already encrypted with the starter
kit's demo `N8N_ENCRYPTION_KEY` (`super-secret-key`). This deployment's key
comes from Bitwarden, so importing upstream's ciphertext verbatim creates two
credentials that appear in the editor and fail every request.

The vendored files under `roles/n8n_k8s/files/starter-kit/credentials/` instead
carry `data` as a **plaintext object**. `n8n import:credentials` encrypts an
object-valued `data` with the running instance's own key, so the imported
credentials are valid here. Upstream ids and names are preserved so the demo
workflow resolves them without edits. The offline suite asserts `data` is an
object — a string would mean the ciphertext bug is back.

### Ollama model

`ollama pull` cannot run as a separate init container against a server in
another container, so the Deployment starts `ollama serve` in the background,
waits for it to answer, then pulls `n8n_k8s_starter_kit_ollama_model`
(`llama3.2`, which the demo workflow references as `llama3.2:latest`). The pull
is best-effort: a registry failure logs a warning and leaves a working server
rather than crash-looping. Readiness is `GET /api/tags`, so the pod becomes
ready as soon as the server is up — the model download does not block the Helm
upgrade.

The model lands on the PVC, so a pod restart re-runs the pull as a no-op. This
node has no GPU and no device plugin, so `cpu` is the only profile proven here;
`gpu-nvidia` / `gpu-amd` add `nvidia.com/gpu` / `amd.com/gpu` requests, which
will leave the pod `Pending` on a node without the matching plugin.

### Pod Security Standards

The `n8n` namespace enforces `restricted`. Every kit workload therefore runs
`runAsNonRoot` 1000:1000 with `fsGroup: 1000`, `seccompProfile:
RuntimeDefault`, `allowPrivilegeEscalation: false`, and all capabilities
dropped. Two consequences worth knowing:

- Ollama's image defaults models to `$HOME/.ollama` where `$HOME` is `/root`,
  which uid 1000 cannot write; `HOME` and `OLLAMA_MODELS` are repointed at the
  mounted claim.
- Qdrant's default snapshot path is not writable either, so snapshots go to an
  `emptyDir` and storage to the claim.

A workload missing any of these is rejected at admission, so the deploy fails
loudly rather than degrading. The offline suite asserts it before shipping.

### PostgreSQL is deliberately not adopted

n8n here runs on SQLite on PVC `n8n`. Standing up the kit's PostgreSQL and
repointing n8n at it is **not** a values change — it is a data migration, and
flipping the flag back does not undo it. The role refuses the combination:
`n8n_k8s_starter_kit_postgres_adopt` must stay `false`, and the preflight fails
with that explanation if it is set.

To do it as its own change: take and verify the SQLite backup above, enable
`n8n_k8s_starter_kit_postgres_enabled`, escrow
`N8N_K3S_DEFAULT_POSTGRES_PASSWORD` in the Bitwarden project, migrate the data
deliberately, and only then repoint `database.*`. The rollback path is
**restore-from-backup**, not a Helm rollback.

### Starter kit verification

```bash
kubectl -n n8n get deploy,svc,pvc -l app.kubernetes.io/part-of=n8n-starter-kit
kubectl -n n8n get pod -l app.kubernetes.io/part-of=n8n-starter-kit \
  -o jsonpath='{range .items[*].status.containerStatuses[*]}{.name}{"  "}{.imageID}{"\n"}{end}'

# the import hook's own record
kubectl -n n8n logs job/n8n-starter-kit-import

# demo workflow and credentials are actually in the instance
POD=$(kubectl -n n8n get pod -l app.kubernetes.io/instance=n8n -o name | head -1)
kubectl -n n8n exec "$POD" -c n8n-main -- n8n list:workflow

# the services the demo credentials point at, from inside the n8n pod
kubectl -n n8n exec "$POD" -c n8n-main -- sh -c \
  'wget -qO- http://ollama:11434/api/tags; echo; wget -qO- http://qdrant:6333/readyz'
```

Expected: Deployments `ollama` and `qdrant` `1/1`; pod image IDs reporting the
pinned digests above; `n8n list:workflow` containing `srOnR8PAY3u4RSwb` ("Demo
workflow"); `/api/tags` listing `llama3.2:latest` once the pull finishes; and
`/readyz` reporting Qdrant ready.

The role asserts the first three after every run, so a kit workload that did
not come up fails the play instead of passing silently.

## Verification

```bash
kubectl -n n8n get deploy,pod,svc,pvc,ingress
helm status n8n -n n8n
helm history n8n -n n8n
helm get values n8n -n n8n
kubectl -n n8n get ingress n8n-main -o wide
kubectl -n n8n get pod -l app.kubernetes.io/instance=n8n \
  -o jsonpath='{range .items[*].status.containerStatuses[*]}{.name}{"  "}{.imageID}{"\n"}{end}'
```

Expected live state from the completed Helm installation:

- Helm release `n8n` is `deployed`.
- Deployment `n8n-main` is `1/1` available.
- Pod has `2/2` containers ready: n8n and task-runner.
- Pod image IDs report the pinned digests: `sha256:e29e9cc9...` for n8n and `sha256:1f53745a...` for the task runner.
- PVC `n8n` is `Bound` with `10Gi` on `local-path`.
- Ingress is class `tailscale` and reports `n8n.tailf99a0.ts.net`.

Application-level health, through the tailnet path a client actually uses:

```bash
curl -sk https://n8n.tailf99a0.ts.net/healthz   # {"status":"ok"}
```

### Known harmless warnings

The `kubernetes.core.helm` task emits two warnings that do not indicate a
problem with this release:

- `The default idempotency check can fail to report changes in certain
  cases. Install helm diff >= 3.4.1 for better results.` Helm's built-in
  idempotency check is approximate. The role compensates by asserting the
  deployed state independently: it waits for the Deployment to become
  available and then asserts the running pods report the pinned image
  digests.
- `The 'status.values' return value is deprecated and will be removed in
  version 8.0.0. Use 'status.release_values' instead.` This warning comes
  from inside the collection, not from this role. The role registers the
  Helm result but does not read `status.values`; the deployment, pod, and
  ingress facts it asserts on come from separate `kubernetes.core.k8s_info`
  calls. Nothing needs to change here until `kubernetes.core` 8.0.0 is
  installed, at which point the warning disappears.

## Tailnet Lock prerequisite

The generated proxy currently cannot serve traffic until its node is signed by a trusted Tailnet Lock signing device. The live proxy reported:

`this node is locked out; it will not have connectivity until it is signed`

The node key is shown only in the operator diagnostics. A tailnet administrator must sign that exact pending n8n node from a trusted signing device. This is an external Tailscale control-plane action; the Helm release and Kubernetes resources are already deployed.

`noesis-praxis` is a Tailnet Lock signing node, so a new proxy nodekey can be signed there with `sudo tailscale lock sign nodekey:<key>`.
