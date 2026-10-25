# OpenClaw deployment runbook

Deployment of **upstream OpenClaw** (<https://github.com/openclaw/openclaw>)
onto the Noesis k3s cluster and onto plain hosts.

> **Do not confuse this with AlphaClaw.** `roles/openclaw` and
> `playbooks/openclaw.yml` deploy **AlphaClaw** (`garrytan/alphaclaw`, port
> 8090) — a different product that merely shares the name. It is intentionally
> untouched. Everything below is upstream OpenClaw.

---

## 1. Release pin

| Item | Value | Where it is pinned |
| --- | --- | --- |
| Upstream release | `v2026.10.7` (published 2026-10-24, latest non-prerelease) | `roles/openclaw_*/defaults/main.yml` |
| Container image | `ghcr.io/openclaw/openclaw:2026.10.7-slim` | chart `values.yaml` |
| Image digest | `sha256:fb26f0841659dc757f23feec9adeab51f11d76779a409db5d22e191b43841afa` | chart + all three roles |
| Helm chart | `charts/openclaw/0.3.2` (Noesis-maintained, **not** an official upstream chart) | `charts/openclaw/` |
| Node runtime | Node 24.22.1+ / 26.12.1+ | upstream requirement |

The digest is the **multi-architecture OCI index** for the tag, confirmed to
carry `linux/amd64` and `linux/arm64`. The deployment pulls **by digest**, so a
retagged release cannot drift underneath the pin.

Upstream publishes **no Helm chart**. Their docs state the Kustomize manifests
in `scripts/k8s/manifests/` are the reference, and that a Helm chart is the
right answer for a more complex deployment — which is what this repo maintains.

---

## 2. The three install methods

All three are dispatched from one playbook:

```
playbooks/openclaw-deploy.yml
```

| Method | Role | Upstream mechanism |
| --- | --- | --- |
| `host` | `roles/openclaw_host` | `https://openclaw.ai/install.sh` (the vendor's own installer) |
| `docker` | `roles/openclaw_docker` | upstream `docker-compose.yml`, adapted to a digest-pinned image |
| `k8s` | `roles/openclaw_k8s` | Noesis Helm chart `charts/openclaw/0.3.2` |

Every method is **fail-closed**: live, state-changing work is opt-in per run
(`openclaw_host_live_changes` / `openclaw_docker_live_changes` /
`openclaw_k8s_live_checks`), and the role refuses to run without it.

### 2.1 Kubernetes (Helm) — the deployed method

```bash
export ANSIBLE_VAULT_PASSWORD_FILE=/home/elvis/.hermes/cache/scratch/dummy_vault_pass
cd /home/elvis/projects/noesis-ansible

ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/openclaw-deploy.yml \
  -e openclaw_deploy_method=k8s \
  -e openclaw_k8s_existing_secret=openclaw-secrets \
  -e openclaw_k8s_exposure_enabled=true \
  -e openclaw_k8s_kube_context=default \
  -e openclaw_k8s_storage_class=local-path \
  -e openclaw_k8s_live_checks=true
```

Target group: `openclaw_k3s` in `inventory/praxis-k3s/hosts.ini` (host
`noesis-lab`). Override with `-e openclaw_deploy_group=<group>`.

### 2.2 Docker / Compose

```bash
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/openclaw-deploy.yml \
  -e openclaw_deploy_method=docker \
  -e openclaw_docker_live_changes=true
```

Requires `/opt/openclaw-docker/.env` to exist with `OPENCLAW_GATEWAY_TOKEN`
(provisioned out of band; the role never generates or inlines a credential).

### 2.3 Host install

```bash
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/openclaw-deploy.yml \
  -e openclaw_deploy_method=host \
  -e openclaw_host_live_changes=true
```

Runs the vendor installer non-interactively (`--no-prompt --no-onboard`),
installs a hardened systemd unit, and requires
`/etc/openclaw/openclaw.env` (mode 0600, owner `openclaw`) to already carry
the token.

---

## 3. Tailnet exposure

The Control UI is published to the tailnet by a **Tailscale Ingress**
(`ingressClassName: tailscale`), which makes the operator mint a **separate
proxy device** named after the service.

| Setting | Value |
| --- | --- |
| Service name / device name | `noesis-openclaw` |
| MagicDNS name | `noesis-openclaw.tailf99a0.ts.net` |
| Tailnet domain | `tailf99a0.ts.net` |
| IngressClass | `tailscale` |
| Gateway bind | `lan` |

Three things must agree, and the chart **fails closed** if they do not:

1. **`ingress.host` is a bare hostspec** (`noesis-openclaw`), never a `*.ts.net`
   FQDN. The operator appends the tailnet domain itself.
2. **`gateway.bind` is `lan`** when exposure is on. `loopback` is reachable only
   via `kubectl port-forward`; a Tailscale Ingress against it returns 502.
3. **`gateway.allowedOrigins` contains the browser's real origin** —
   `https://noesis-openclaw.tailf99a0.ts.net`, i.e. host **and** domain. The
   Control UI validates the origin the browser actually sends; a bare
   `https://noesis-openclaw` loads the UI and then refuses every request.
4. **`gateway.trustedProxies` lists the proxy.** The operator's Ingress
   forwards `X-Forwarded-For`, and the gateway **fails closed** with
   `403 proxy_attribution_required` on any request carrying proxy headers from
   a source it does not trust. Without this the UI loads but every request is
   rejected. The value is the cluster's **pod CIDR** (`10.42.0.0/24` on
   noesis-praxis), because the operator's proxy pods take dynamic IPs and a
   single IP would break on every reschedule. Read the real value with
   `kubectl get nodes -o jsonpath='{.items[0].spec.podCIDR}'`.

`openclaw_k8s_reserved_hostnames` lists names the proxy must never claim
(`tailscale-operator`, `noesis-praxis`, `noesis-lab`). The operator mints a
device per Ingress, so claiming an existing name **hijacks** that identity and
the original endpoint stops resolving to its real backend.

### Reaching it

Use the hostname and the scheme. There is no plaintext listener on :80, and the
service's container port is cluster-internal — an IP plus a port is not a usable
endpoint.

```
https://noesis-openclaw.tailf99a0.ts.net/
```

The Control UI authenticates with the gateway token from the `openclaw-secrets`
Secret (Bitwarden record `OPENCLAW_K3S_NOESIS_GATEWAY_TOKEN`).

---

## 4. Credential handling

Store **before** deliver, deliver **before** expose.

1. Generate the gateway token and escrow it:

   ```bash
   openssl rand -hex 32
   bws secret create OPENCLAW_K3S_NOESIS_GATEWAY_TOKEN "<value>" <project-id> \
     --note "OpenClaw gateway token for the k3s release 'openclaw' in ns openclaw."
   ```

2. Deliver it as the Secret the chart references (`existingSecret`):

   ```bash
   kubectl -n openclaw create secret generic openclaw-secrets \
     --from-file=OPENCLAW_GATEWAY_TOKEN=/path/to/token \
     --dry-run=client -o yaml | kubectl apply -f -
   ```

The chart **never creates a Secret** and the role never inlines a credential.
`existingSecret` must name a pre-existing Secret.

---

## 4b. How a config change reaches the running gateway

Two things stand between a chart edit and the running process. Both were
found the hard way; both are asserted by the offline suite.

**The seed must MERGE, not only seed.** The upstream pattern copies
`openclaw.json` from a ConfigMap **only if the file is missing**. On a
persistent volume the file always exists, so a settings change is silently
ignored — the ConfigMap updates, the pod keeps the config it started with.
The chart's init container therefore **merges the chart-owned top-level keys**
(`gateway`, `cron`) into the live config and leaves everything else alone.
Overwriting the whole file instead would discard app-owned state (channels,
agents, plugin config).

**The pod must roll.** A ConfigMap change does not restart anything, so the
Deployment carries a `checksum/config` annotation over the rendered ConfigMap.
Without it the merged config lands on disk but the gateway never re-reads it.

**Bump the chart version.** `kubernetes.core.helm` **skips the upgrade when the
chart version is unchanged**, even if the chart's content changed: the run
reports `ok` / `changed=0` and the release keeps the old chart. Chart
versions are immutable artifacts — every content change gets a new version
(`charts/openclaw/0.2.0/` → `0.2.1/`), and the role pins
`openclaw_k8s_chart_version`.

## 4c. Gateway auth-token escrow

The Gateway's auth-token is `gateway.auth.token` as the Gateway **resolves it** —
i.e. the value delivered in the Secret. It is escrowed in Bitwarden as
`OPENCLAW_K3S_NOESIS_GATEWAY_TOKEN` in project `72974d0e-81af-4678-bab7-b46000985859`.

Escrowing the Gateway's *own* value — rather than a copy of what we intended to
deliver — is what keeps the escrow authoritative. The deploy captures the live
token and asserts it equals the delivered Secret, so a divergence is a hard
failure instead of a mystery later.

```bash
# during a deploy (opt-in: it WRITES to Bitwarden)
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/openclaw-k8s-install.yml \
  -e openclaw_k8s_existing_secret=openclaw-secrets \
  -e openclaw_k8s_exposure_enabled=true \
  -e openclaw_k8s_kube_context=default \
  -e openclaw_k8s_storage_class=local-path \
  -e openclaw_k8s_live_checks=true \
  -e openclaw_k8s_authtoken_escrow_enabled=true \
  -e openclaw_k8s_bws_project_id=72974d0e-81af-4678-bab7-b46000985859
```

It is **idempotent**: the escrow is written only when the record is missing or
no longer matches the Gateway's token, so a converging deploy never rewrites a
credential. If the Gateway has no token at all, set
`openclaw_k8s_authtoken_generate=true` to let the deploy run
`openclaw doctor --generate-gateway-token` and then escrow the result.

### Revealing the token by hand

`openclaw gateway auth-token --show` **refuses to run outside an interactive
terminal** — it checks both `stdin.isTTY` and `stdout.isTTY` so the token
cannot end up in a pipe or a captured log. To capture it to a file, allocate a
pty inside the container:

```bash
POD=$(kubectl -n openclaw get pod -l app.kubernetes.io/name=openclaw -o jsonpath='{.items[0].metadata.name}')
kubectl -n openclaw exec "$POD" -c gateway -- \
  script -qec "node dist/index.js gateway auth-token --show" /dev/null > token.txt
```

`script` is present in the image. Never print the file — compare hashes only.

## 4d. Device pairing approvals

The device CLI lives inside the pod (the binary and the pairing state are in
the image and on the PVC), so pairing operations run there via `kubectl exec`.

```bash
# what is waiting?
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/openclaw-k8s-device.yml \
  -e openclaw_device_action=list

# approve one specific request
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/openclaw-k8s-device.yml \
  -e openclaw_device_action=approve \
  -e openclaw_device_request_id=0f4036f5-f5cd-4e81-a2ce-31f1ed623352

# approve the most recent pending request
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/openclaw-k8s-device.yml \
  -e openclaw_device_action=approve-latest

# reject
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/openclaw-k8s-device.yml \
  -e openclaw_device_action=reject \
  -e openclaw_device_request_id=<id>
```

`approve` and `reject` **require an explicit request id** — a pairing approval
grants Gateway access, so it is never implicit. `approve-latest` keeps the
CLI's own two-step safety property: the implicit selection is a *preview* that
prints the request id, and the approval is bound to that exact id.

A paired device shows up in `devices list` with its role and scopes.

## 4e. Plugins and the decision model (TypeSafe)

The Gateway loads plugins from the state volume. The chart installs declared
plugin packages in the `seed-config` init container, so a fresh PVC comes up
with the plugin already present.

### What the chart owns

| Piece | Where | Value |
|---|---|---|
| package | `values.yaml → plugins.install` | `@openclaw/typesafe@2026.10.7` |
| allowlist | `values.yaml → plugins.allow` | `["typesafe"]` |
| credential | `values.yaml → plugins.entries.typesafe.config.apiKey` | `{source: store, provider: default, id: TYPESAFE_API_KEY}` |
| decision model | `values.yaml → agents.defaults.decisionModel` | `typesafe/jev-latest` |
| pinned agent | `values.yaml → agents.entries.research.decisionModel` | `typesafe/jev-1.13.0` |
| store write | `values.yaml → secretStore.entries` | `TYPESAFE_API_KEY` from the Secret's env |

The credential is a **SecretRef**, never a literal. The value lives in the
Gateway's team-scoped SQLite secret store, written by the init container from
the `existingSecret` environment variable.

### The three things that break the install

1. **The temp root.** The plugin installer refuses a group/world-writable
   root without the sticky bit:

   > temp workspace ancestor /tmp has group/world-writable mode 2777 without
   > sticky protection … have its administrator restore safe permissions
   > (1777 for a shared system temp directory)

   The emptyDir behind `/tmp` is created 2777 and the container runs as uid
   1000, so it cannot fix a root-owned directory itself. The `prepare-temp`
   init container runs as root for exactly one command — `chmod 1777 /tmp` —
   with `readOnlyRootFilesystem`, no privilege escalation and every capability
   dropped. `TMPDIR` does **not** satisfy the check.

2. **Memory.** The install is an npm install. The container's old 64Mi limit
   OOMKilled it mid-install (exit 137). It now requests 256Mi and is capped at
   512Mi. npm's cache is pointed at the volume (`npm_config_cache`), because
   `$HOME/.npm` is on the read-only rootfs.

3. **`--value` is refused.** For a secret-kind entry the store CLI rejects
   `--value` (it would leak through argv). The value is piped:

   ```sh
   printenv TYPESAFE_API_KEY | node /app/dist/index.js secrets store set \
     TYPESAFE_API_KEY --value-file -
   ```

   Note: `${ TYPESAFE_API_KEY }` is *not* valid POSIX expansion (`sh: Bad
   substitution`), and `${...}` collides with Helm's `{{{` syntax anyway.
   `printenv` avoids both.

### Skip-if-installed

The install is skipped when the plugin is already in the **persisted registry**:

```sh
node /app/dist/index.js plugins list --json | grep -q '"id": "typesafe"'
```

Do not check a path. The layout depends on the package — the install landed in
`npm/projects/openclaw-typesafe-<hash>`, not `extensions/<name>` — so a path
check re-installs on every pod start.

### Ownership of the agent set

`agents.ownership: "explicit"` with more than one agent means owner-scoped
commands have no implicit owner:

> Multiple agents are configured, but model inspection has no explicit owner.
> Pass `--agent <id>` or set agents.defaults.systemAgent.agentId.

`agents.defaults.systemAgent.agentId` is set to `default` so `models status`
and friends work without a flag. Heartbeats stay **disabled**: they need
`agents.defaults.heartbeat.agentId`, which is deliberately unset (the chart
also disables automations).

### Delivering the credential

```bash
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/openclaw-k8s-secret.yml \
  -e openclaw_k8s_bws_project_id=72974d0e-81af-4678-bab7-b46000985859 \
  -e openclaw_k8s_existing_secret=openclaw-secrets \
  -e openclaw_k8s_kube_context=default
```

The playbook maps `TYPESAFE_API_KEY` (Bitwarden) → the `TYPESAFE_API_KEY` key
of the `existingSecret`. The chart never creates a Secret.

### Proving the credential resolves

`openclaw secrets audit` does **not** cover plugin-config paths — a bogus
SecretRef id still audits clean. Use the plugin's own readiness instead:

```bash
POD=$(kubectl -n openclaw get pod -l app.kubernetes.io/name=openclaw -o jsonpath='{.items[0].metadata.name}')
kubectl -n openclaw exec "$POD" -c gateway -- node dist/index.js gateway call \
  plugins.inspect --params '{"pluginId":"typesafe"}' --json
```

```json
{ "providerId": "typesafe", "configured": true,
  "credentialReady": true, "callable": true }
```

`credentialReady` is the plugin's `isReady()`, which is
`Boolean(config.baseUrl || config.apiKey)`. With no `baseUrl` configured, a
true value can only come from the resolved store value.

## 5. Verification

What counts as evidence, in order:

```bash
# 1. the release
helm list -n openclaw                     # openclaw  openclaw-0.3.2  deployed
kubectl -n openclaw get pods              # 1/1 Running, 0 restarts

# 2. the operator minted the identity
kubectl -n tailscale get pods -o wide | grep openclaw
kubectl -n tailscale logs deploy/tailscale-operator --tail=200 | grep -i openclaw
#   "exposing ingress over tailscale"  Ingress=openclaw/openclaw

# 3. the backend answers THROUGH the proxy path
kubectl -n tailscale exec ts-openclaw-* -- \
  wget -q -S -O /dev/null http://10.43.84.137:18789/healthz

# 4. the client path -- expect 200 and the Control UI
curl -s -o /dev/null -w '%{http_code}\n' https://noesis-openclaw.tailf99a0.ts.net/
#   200
curl -s https://noesis-openclaw.tailf99a0.ts.net/ | grep -o '<title>[^<]*</title>'
#   <title>OpenClaw Control</title>
```

A `403` here is almost never an auth problem. Read the body — it names the
cause:

| Body | Meaning | Fix |
| --- | --- | --- |
| `proxy_attribution_required` | the proxy is not in `gateway.trustedProxies` | set it (see §3) |
| anything else | — | check the gateway log |

The gateway also logs the exact source it saw, which is how the trusted proxy
address is identified:

```
[gateway] observed unattributable proxy-shaped traffic from 10.42.0.30;
Configure gateway.trustedProxies narrowly ...
```

DNS expectations (MagicDNS names are private — public resolvers return NXDOMAIN
**by design**):

```bash
dig +noall +comments noesis-openclaw.tailf99a0.ts.net @100.100.100.100   # NOERROR
dig +noall +comments noesis-openclaw.tailf99a0.ts.net @1.1.1.1           # NXDOMAIN (normal)
```

Tailnet boundary check — nothing may be published publicly:

```bash
kubectl get svc -A --no-headers | grep -i LoadBalancer   # expect nothing
kubectl get ingress -A --no-headers                        # CLASS column == tailscale
```

---

## 6. Upstream contract notes

Two upstream behaviours drove chart changes; both are asserted by the offline
suite so a future edit cannot silently reintroduce them.

**Probe routes return different JSON keys.** From
`src/gateway/server-http-probes.ts`:

| Route | Body |
| --- | --- |
| `/startupz` | `{"ok": bool, "status": "started"\|"starting"}` |
| `/readyz` | `{"ready": bool}` |
| `/healthz` | `{"ok": bool, "status": "live"}` |

Asserting `.ready` against `/startupz` is **always false** (the key is absent),
which deadlocks the pod in a startup-probe failure loop. Each probe is matched
to its own key.

**Probes must assert the body, not just the status code.** The Control UI
serves a catch-all `200` for unknown paths, so a status-only check passes
forever against an image whose probe route does not exist.

---

## 7. Offline validation

```bash
python3 tests/openclaw/test_offline.py     # 18 checks
helm lint charts/openclaw/0.3.2
helm template openclaw charts/openclaw/0.3.2 \
  --set existingSecret=openclaw-secrets \
  --set ingress.enabled=true --set ingress.className=tailscale \
  --set ingress.host=noesis-openclaw --set ingress.tailnetDomain=tailf99a0.ts.net \
  --set gateway.bind=lan \
  --set 'gateway.allowedOrigins[0]=https://noesis-openclaw.tailf99a0.ts.net'
```

Lint the **rendered** manifests, not the templates — `yamllint` cannot parse
`{{- }}` at all.

The suite carries a `__main__` runner on purpose: a pytest-style file with no
runner is a **silent no-op** when executed as a script — it exits 0 having
asserted nothing.

---

## 8. Tailnet Lock (resolved — but it will recur)

> **Resolved on 2026-10-25.** The proxy device was signed from the MacBook
> (which holds the tailnet's trusted signing key `tlpub:96f144b3…`). The
> Control UI is reachable at <https://noesis-openclaw.tailf99a0.ts.net/>.
> Read the rest of this section before deploying the **next** Tailscale
> Ingress: every new proxy device starts locked out until it is signed.

The tailnet has **Tailnet Lock** enabled with a single trusted signing key
(`tlpub:96f144b3…`). This host's own lock key (`tlpub:2e306822…`) is
different, so **this host cannot sign nodes**.

A newly created proxy device is therefore locked out on creation:

```
tailscale lock status
  The following nodes are locked out by tailnet lock and cannot connect to other nodes:
      noesis-openclaw.tailf99a0.ts.net.  100.98.13.24,…  nodekey:0b3b0ff9…
```

The device registers correctly (it holds a valid ACME certificate and shows
`Online: True` from inside the proxy pod) but has **no tailnet connectivity**,
so the MagicDNS name does not resolve and clients cannot reach it.

**Fix — run from a tailnet-lock signing device:**

```bash
tailscale lock sign nodekey:0b3b0ff9bda719189c091306dc71fda1931f6e39b7702785d881f658b8220d18
```

Signing devices are listed in the Tailscale admin panel. This is a one-time
action per new device; existing signed devices are unaffected.

Until it is signed, the service is fully healthy **in-cluster** but not
reachable over the tailnet.
