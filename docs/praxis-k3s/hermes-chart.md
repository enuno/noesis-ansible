# hermes-agent Chart (jyje) 1.21.0 — Values Key Map & Security Findings

Source of truth: the pinned vendored chart at `charts/vendor/hermes-agent/`
(chart 1.21.0, app v0.22.2). Every key below was verified against the
chart's `values.yaml`, `values.schema.json` (top-level keys +
per-object properties), and every template in `templates/`.
**No key is used that does not exist in this exact chart version.**

## 1. Values key map

### Workload / single-writer

| Capability | Key | Default (chart) | Notes from template inspection |
|---|---|---|---|
| Workload kind | `controller.type` | `deployment` | `deployment` or `statefulset`. Both render the same pod spec. |
| Replicas | `replicaCount` | `1` | Chart documents values >1 as unsupported (single-writer HERMES_HOME). Role hard-pins `1`. |
| **Recreate rollout** | *(forced)* | — | `templates/deployment.yaml` forces `strategy.type: Recreate` when `persistence.enabled` — new pod cannot race the old one for the RWO volume. Requirement satisfied by Deployment; no chart key needed. |
| Pod annotations / labels | `podAnnotations` / `podLabels` | `{}` | |
| Rollout trigger | *(checksum annotations)* | — | Pod template carries `checksum/config` + `checksum/secret` (+ `checksum/team-skill` in team mode), so config/secret changes roll the pod automatically. |

### Persistence (HERMES_HOME)

| Capability | Key | Default (chart) | Notes |
|---|---|---|---|
| Enable | `persistence.enabled` | `true` | |
| StorageClass | `persistence.storageClass` | `""` (cluster default) | Role sets `local-path` (validated k3s SC), configurable. |
| Access modes | `persistence.accessModes` | `[ReadWriteOnce]` | RWO → single-writer. |
| Size | `persistence.size` | `5Gi` | Configurable in role. |
| **Mount path (= HERMES_HOME)** | `persistence.mountPath` | `/opt/data` | Env `HERMES_HOME` is set to this value in both init and main containers; PVC `data` mounts there. |
| Existing claim | `persistence.existingClaim` | `""` | Skip chart PVC creation and bind this claim instead. PVC-retention escape hatch (see §3). |
| Deployment-mode PVC name | *(derived)* | `<fullname>` | Standalone PVC named after the release (e.g. `hermes-agent`). |
| StatefulSet-mode claim | *(derived)* | `data-<fullname>-0` | volumeClaimTemplates, only when `controller.type=statefulset`. |

### Dashboard (management UI)

| Capability | Key | Default (chart) | Notes |
|---|---|---|---|
| Enable | `dashboard.enabled` | `false` | Renders `HERMES_DASHBOARD=1`. In-container binds `0.0.0.0:9119` (override via `HERMES_DASHBOARD_HOST`/`_PORT` env). |
| Public origin | `dashboard.publicUrl` | `""` | Feeds `config.dashboard.public_url` at seed time; needs `bootstrap.overwrite=true` to change later. |
| Trusted proxies | `dashboard.trustedProxies` | `[]` | Feeds `config.dashboard.trusted_proxies`; upstream rejects `0.0.0.0/0`. |
| Readiness probe | `dashboard.readinessProbe.enabled` / `.periodSeconds` | `true` / `10` | TCP readiness on `service.port` (9119) — pod joins Service only when the dashboard listens. Overridden by explicit `probes.readiness`. |
| **Auth provider selector** | `dashboard.auth.provider` | `basic` | One of `basic`, `oauth`, `oidc`, `external`. Template **fails the render** if enabled with `basic` and no `HERMES_DASHBOARD_BASIC_AUTH_USERNAME` + (`_PASSWORD` or `_PASSWORD_HASH`) in `env`/`extraEnv`; `external` skips the check for credentials arriving via `extraEnvFrom`/ExternalSecret. |
| **Password auth** | *(env keys)* | — | `HERMES_DASHBOARD_BASIC_AUTH_USERNAME`, `HERMES_DASHBOARD_BASIC_AUTH_PASSWORD` or `HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH`. **No `existingSecret`-style key exists.** The role applies an operator-managed Secret, keeps provider credentials in `extraEnvFrom`, and references dashboard keys explicitly through `extraEnv[].valueFrom.secretKeyRef`; `dashboard.auth.provider` remains `basic` so Hermes—not Tailscale Serve—enforces authentication. |

### Service

| Capability | Key | Default (chart) | Notes |
|---|---|---|---|
| Create Service | `service.enabled` | `false` | |
| Service type | `service.type` | `ClusterIP` | No NodePort/LoadBalancer by default; role pins ClusterIP explicitly. |
| Legacy port | `service.port` | `9119` | Used when `service.ports` is empty; targetPort = same value. |
| Explicit ports | `service.ports` | `[]` | List of `{name, port, targetPort, protocol}`; non-empty list replaces legacy port and also renders matching container `ports`. Role uses this for the dashboard port. |
| Annotations | `service.annotations` | `{}` | |

### Secrets / external secret mechanisms

| Capability | Key | Default | Notes |
|---|---|---|---|
| Chart-managed env Secret | `env` (map) | placeholder `OPENAI_API_KEY` | Rendered as Secret `<fullname>-env`, injected via `envFrom` on main container, device-login init, and test Job. `values.schema.json` **requires the `env` key to exist** (may be `{}`). |
| **External reference (our path)** | `extraEnvFrom` | `[]` | Standard `envFrom` entries (`secretRef`/`configRef`). The chart's supported mechanism for externally-managed Secrets. Every chart-owned envFrom (main container, device-login init, test Job) is appended with these entries. |
| ESO integration | `externalSecret.enabled` + `externalSecret.{refreshInterval,secretStoreRef,target,data,dataFrom}` | `false` | Replaces the chart's own Secret with an External Secrets Operator `ExternalSecret` (requires ESO CRDs installed). **Not used** — minimal k3s has no ESO; `externalSecret.enabled` also *stops* `secret.yaml` rendering. |
| Arbitrary extra manifests | `extraResources` | `[]` | `tpl`-rendered raw YAML (e.g. SealedSecret). |

### ServiceAccount / API access

| Capability | Key | Default | Notes |
|---|---|---|---|
| Create SA | `serviceAccount.create` | `true` | |
| SA name | `serviceAccount.name` | `""` (fullname-derived) | |
| Annotations | `serviceAccount.annotations` | `{}` | |
| **Automount token** | `serviceAccount.automountServiceAccountToken` | `false` | Rendered explicitly on the pod spec (line `automountServiceAccountToken:` in `_helpers.tpl`). Chart sets the safe default; role pins `false`. |

### Network policy

| Capability | Key | Default | Notes |
|---|---|---|---|
| Enable | `networkPolicy.enabled` | `false` | |
| DNS egress | `networkPolicy.allowDns` + `networkPolicy.dns.{namespaceSelector,podSelector}` | `true` / kube-system+kube-dns | |
| Block private egress | `networkPolicy.blockPrivateEgress` | `true` | Egress allowed to public internet only; RFC1918 + link-local/metadata `169.254.0.0/16` and ULA/link-local v6 blocked. Set false (or use `extraEgress`) for in-cluster proxies. |
| Extra rules | `networkPolicy.extraEgress` / `extraIngress` | `[]` | `ingress:` renders **empty = deny all inbound** (intended default; gateway is outbound-only). Praxis deploy values add ONE extraIngress rule: dashboard TCP 9119 from `hermes_agent_dashboard_ingress_cidr` (k3s node /32) for the host-level Tailscale Serve path. |

### Security contexts / hardening

| Capability | Key | Default | Notes |
|---|---|---|---|
| Pod securityContext | `podSecurityContext` | `{}` | Empty for s6-overlay compat. Chart's `values-hardened.yaml` provides PSS-`restricted`-verified overlay: `runAsNonRoot: true, runAsUser/Group/fsGroup: 10000, seccompProfile: RuntimeDefault`. |
| Container securityContext | `securityContext` | `{}` | Hardened overlay: `allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: drop [ALL]`. Both verified working with the pinned image when `/run` + `/tmp` are writable tmpfs. |
| Writable tmpfs | `extraVolumes` + `extraVolumeMounts` | `[]` | Hardened overlay adds `emptyDir{medium: Memory, sizeLimit}` at `/run` (16Mi) and `/tmp` (64Mi). **Caveat**: helm replaces arrays wholesale across `-f` files — merge lists manually. |
| Resources | `resources` | req 100m/256Mi, lim 2/2Gi | Role keeps chart defaults (configurable). |
| Runtime class | `runtimeClassName` | `""` | Optional gVisor/Kata kernel boundary. |

### Probes

| Key | Default | Notes |
|---|---|---|
| `probes.startup` / `probes.liveness` / `probes.readiness` | `{}` (none) | Full probe spec passthrough. s6-overlay already supervises in-container restarts; chart renders dashboard TCP readiness when `dashboard.readinessProbe.enabled`. Role relies on dashboard readiness (app-level signal: dashboard listener up behind auth gate) and sets no liveness (avoid kill-loops during long first boot). |

### Hooks / tests

| Item | Finding |
|---|---|
| Install/upgrade hooks | **None.** Only the helm-test Job below + ArgoCD `PostSync` annotation. |
| `tests.enabled` | `true` → renders Job `<fullname>-test` with `helm.sh/hook: test`, `hook-weight: 1`, `hook-delete-policy: before-hook-creation`, `backoffLimit: 0`, `restartPolicy: Never`. |
| **What the chart test proves** | (1) `hermes --version` runs in the pinned image; (2) seeded `config.yaml` exists in HERMES_HOME; (3) docker absence is expected under `terminal.backend: local`; (4) `hermes doctor` runs (`doctorStrict: false` → issues logged, non-fatal); (5) optional `hermes chat` provider round-trip (`tests.chat.enabled`, **off by default**, logs the full conversation). |
| **Second-writer safety** | ✅ The test Job mounts `data` as **emptyDir** (its own private HERMES_HOME) — it never touches the live PVC. No replacement needed. |
| Test credentials | Test container inherits `envFrom` (chart env Secret + `extraEnvFrom`), so our provider Secret is referenced there too; with placeholder/missing keys, `doctor` reports issues non-fatally. |

### Not used (kept at chart defaults, documented)

| Key | Default | Why off |
|---|---|---|
| `apiServer.enabled` / `webhook.enabled` | `false` | Inbound listeners not required; disabling keeps NetworkPolicy deny-all-ingress correct. |
| `ingress.enabled` / `httpRoute.enabled` | `false` | No Ingress controller on minimal k3s (Traefik disabled); dashboard reached via `kubectl port-forward`. |
| `auth.deviceFlow.enabled` | `false` | Interactive OAuth device login not needed for a static provider key. When enabled it adds a `python:3.13-slim` init container that runs as root by default (see §2). |
| `team.enabled` | `false` | Multi-agent team protocol / shared RWX knowledge volume not part of the minimal deployment. Its permissions init container is root-only by design. |
| `readyNotify.enabled` | `false` | Startup notification hook; requires messenger credentials. |

## 2. Security findings

1. **Default credential placeholder must be removed.** Chart default `env:
   {OPENAI_API_KEY: "«redacted:sk-…»"}` renders a real Secret containing a
   placeholder key. The role overrides `env: {}` (schema-required key kept)
   and injects real credentials **only** through the operator-managed
   `extraEnvFrom` Secret. Never deploy with the chart default env.
2. **Dashboard fails closed — keep it that way.** On a non-loopback bind the
   upstream auth gate is mandatory; `HERMES_DASHBOARD_INSECURE`/`--insecure`
   are deprecated no-ops. The role keeps `dashboard.auth.provider: basic` and
   supplies the required variable names through explicit
   `extraEnv[].valueFrom.secretKeyRef` entries pointing at the
   operator-managed Secret. Helm can verify the required names at render time
   without receiving the credential values; the deploy role also validates
   password strength before touching the cluster.
3. **Root init containers exist but are avoidable.**
   - `seed-config` (always, when `bootstrap.enabled`): runs the pinned Hermes
     image; when started as root it drops privileges itself via `setpriv`
     for config migration and only chowns the top-level HERMES_HOME + three
     chart-seeded files. With the hardened overlay (pod runs as uid/gid
     10000) it starts non-root and the migration runs directly as that uid.
   - `auth-device-login` (**off by default**): `python:3.13-slim` image,
     `securityContext: {}` → root by default; needs root to chown the token
     to uid 10000. Hardened non-root configuration is documented in
     `values-hardened.yaml` (match `tokenOwner` uid/gid). Not enabled here.
   - `init-team-shared` (team mode only, `team.sharedVolume.permissions.enabled`,
     off by default): hardcoded `runAsUser/Group: 0` chown init — explicitly
     incompatible with PSS `restricted`; the chart itself says to rely on
     `fsGroup` instead. Not enabled here.
4. **Network exposure defaults are safe.** No Service, Ingress, HTTPRoute,
   apiServer, or webhook is created by default; the gateway is outbound-only.
   Enabling the dashboard does not expose it — a Service port must be chosen
   explicitly. Role pins `service.type: ClusterIP` (no NodePort/LoadBalancer/
   Ingress/hostNetwork anywhere) and enables the NetworkPolicy
   (deny-all-ingress except dashboard TCP 9119 from the k3s node /32 via
   `networkPolicy.extraIngress`; DNS-only + public-internet egress, metadata endpoint
   blocked).
5. **Cloud-metadata egress.** The agent executes shell/code inside the pod;
   the chart's NetworkPolicy blocks `169.254.0.0/16` and ULA/link-local v6
   (AWS-style IMDS lives in `fd00::/8`) by default via
   `networkPolicy.blockPrivateEgress: true`.
6. **Helm test runs a Job in the release namespace** with the release's
   Secrets via `envFrom`; `tests.chat` logs the full model conversation when
   enabled (keep off; it is off by default). Test pod uses an emptyDir home,
   not the live PVC.
7. **Artifact Hub vulnerability scan** (informational, 2026-10-18): image
   `nousresearch/hermes-agent:v0.22.2` shows 0 critical / 5 high / 277 medium
   findings in AH's scanner. Mediums are typical of the Python base image;
   there is no patched alternative tag at pin time. Re-check before
   upgrading.

## 3. PVC retention behavior (documented, not assumed)

- Chart-created PVC (`persistence.existingClaim` empty, Deployment mode):
  the rendered PVC (`templates/pvc.yaml`) carries **no** retention annotation,
  so **`helm uninstall` deletes the PVC and all HERMES_HOME state with it**.
  `helm upgrade` / re-run of the deploy role does **not** touch the PVC
  (idempotent install/upgrade; the role never uninstalls).
- Operator-owned claim (`persistence.existingClaim: <name>`): the chart never
  creates or deletes it — retention is fully the operator's. The role exposes
  `hermes_agent_persistence_existing_claim` (default `""`) as the
  retention-safe path; setting it makes the release bind the pre-created PVC
  and renders the chart's PVC template inert.
- Role/playbook policy: **never delete the PVC**; the persistence verify test
  writes a marker, restarts the pod once, verifies, removes the marker, and
  explicitly does not delete the claim.

## 4. Execution model addendum

The chart has no `image.digest` key. The deploy role therefore resolves the
configured tag through Docker Hub's anonymous registry API immediately before
Helm apply and fails closed unless `Docker-Content-Digest` equals the pinned
multi-arch digest. Runtime verification then checks the running imageID against
the accepted manifest-list or amd64 child digest. This is a pre-deploy policy,
not merely a post-deploy claim.

The operational boundary is the k3s server. Both `hermes-deploy.yml` and
`hermes-verify.yml` target `k3s_server`, use sudo, and execute
`kubernetes.core`/Helm on that host against the root-owned
`/etc/rancher/k3s/k3s.yaml`. This eliminates controller-side cluster-admin
credentials. The controller supplies only the vendored chart source and
Ansible templates; the chart is staged at `/opt/hermes-agent-chart` and
rendered values at `/opt/hermes-agent-stage` on the target.

Host dependencies are a checksum-verified Helm **v4.3.1** installed by the
reusable `roles/helm`, plus `kubernetes==34.1.0` in the dedicated target venv
`/opt/ansible-kubernetes`. The venv choice preserves Ubuntu's
externally-managed system Python while giving the remote module interpreter
an exact Kubernetes client pin. Helm install/upgrade uses atomic rollback and
a bounded wait (300 seconds by default).

The verification playbook likewise performs all reads and in-pod execs from
the target. Its only stateful probe writes one unique marker into HERMES_HOME,
deletes exactly one pod (the Deployment recreates it), verifies the marker
after readiness, and removes the marker; it never deletes the PVC. The chart
test remains gated: its isolated emptyDir Job proves `hermes --version`,
chart-seeded config, and non-strict `hermes doctor`, not persistence or
provider connectivity. Real provider traffic remains separately gated and
defaults to **NOT RUN**.
