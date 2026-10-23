# MCPJungle on Kubernetes — Runbook & Provenance

**Status: implemented locally, NOT deployed.** No cluster mutation, no Bitwarden
write, no tailnet policy publish has been performed.

## 1. Why this chart is first-party

The brief named `github.com/dinhdobathi1992/MCPjungle-chart`. **That repository
does not exist** (HTTP 404; GitHub search `MCPjungle-chart` → 0 results). The real
chart lives inside a *fork*: `dinhdobathi1992/MCPJungle` → `mcpjungle-chart/`.

It was **rejected**. Verified findings (2026-10-22):

| Finding | Evidence |
|---|---|
| Image does not exist | `ghcr.io/dinhdobathi1992/mcpjungle:v2.1.0` → HTTP 403 / `DENIED`. Control: official image → HTTP 200 |
| No LICENSE in chart dir | `LICENSE`, `LICENSE.md`, `README.md` all 404 |
| Unmaintained | 3 commits, all 2026-05-03; fork has no CI to build/push the image |
| Invents env vars | `MCPJUNGLE_ADMIN_TOKEN`, `MCPJUNGLE_INIT_TOKEN`, `MCPJUNGLE_SERVERS_FILE` absent from upstream docs **and** upstream Go source |
| Invalid flag | passes `--ui`; upstream defines only `--port --host --sqlite-db-path --enterprise --prod` |
| Wrong dashboard path | NOTES says `/ui`; upstream serves the dashboard at `/` |
| SQLite-only | pins `DATABASE_URL=/data/mcpjungle.db` against upstream's own "not recommended for production or multi-user" guidance |
| Leaves credentials behind | `helm.sh/resource-policy: keep` on the admin Secret |

**No official upstream chart exists.** Upstream issue
[mcpjungle/MCPJungle#56 "Provide an official Helm chart"](https://github.com/mcpjungle/MCPJungle/issues/56)
is **still open**; maintainer `duaraghav8` (2025-08-22): *"We'll soon be working
on a helm chart for mcpjungle."* #72 was closed as a duplicate. No Artifact Hub entry.

**Decision:** repair and own `charts/mcpjungle` in noesis-ansible, pinned to the
**official upstream image**, rather than adopt or vendor a broken third-party chart.

## 2. Pinned provenance

```
image     ghcr.io/mcpjungle/mcpjungle
tag       0.4.6                (upstream release 2026-08-02)
digest    sha256:59940d2e3a586ab9a063cf24fa37460bc993686fa056729fd1ada25436123dd9   (multi-arch index)
          sha256:c953a33f84fd0afaf6553b6682cbc12636717dcb9529407ef179198c180adb1c   (linux/amd64)
          sha256:fc2bf2f008a175f4174f8812d1a90bb7e28f06e054eb70668250da3d6623784d   (linux/arm64)
chart     charts/mcpjungle @ 0.2.0 (noesis-ansible first-party)
licence   upstream MPL-2.0
```

### Verified upstream interface (do not "improve" these)

Env: `DATABASE_URL`, `SQLITE_DB_PATH`, `POSTGRES_HOST/PORT/USER/PASSWORD/DB`
(+ `_FILE` variants), `MCPJUNGLE_BIND_HOST`, `PORT` (8080), `SERVER_MODE`
(`development`|`enterprise`; `production` is a deprecated alias), `OTEL_*`,
`SESSION_IDLE_TIMEOUT_SEC`.

Endpoints: `GET /health` → 200 `{"status":"ok"}` (unauthenticated); `GET /metadata`;
`POST /init`; `ANY /mcp` (streamable HTTP); `ANY /sse` + `ANY /message` (SSE);
`/metrics` when OTEL is on.

Auth: `mcpjungle --registry <url> init-server` mints the admin token.
**No upstream env var pre-seeds it, and there is no documented reset path.**

## 3. Required variables

See `inventory/mcpjungle-k8s/group_vars/all.yml` (committed, credential-free).

Mandatory and enforced:
- `mcpjungle_k8s_kubeconfig` + `mcpjungle_k8s_context` — never implicit. Preflight
  fails closed if the named context is absent from the kubeconfig; it will **not**
  fall back to the ambient current-context.
- `mcpjungle_k8s_image_digest` matching `^sha256:[0-9a-f]{64}$`, and
  `mcpjungle_k8s_image_tag != 'latest'`.
- `mcpjungle_k8s_bw_project_id == "72974d0e-81af-4678-bab7-b46000985859"`.
  Hard equality against the required constant, not a soft default.

### Bitwarden

```
project id : 72974d0e-81af-4678-bab7-b46000985859   ("noosphere", org 93331de5-…)
auth       : machine account access token via BWS_ACCESS_TOKEN (controller side)
write gate : mcpjungle_k8s_k8s_allow_bitwarden_write  (default false — fails closed)
```

**Trust boundary.** The machine account needs *read, write* on that project.
Read access is **verified**; write access is **UNVERIFIED** (see §7).

Escrow keys (deterministic, environment/cluster/release scoped):

| Key | Purpose | Created when |
|---|---|---|
| `MCPJUNGLE_K3S_DEFAULT_DB_PASSWORD` | PostgreSQL password | Pre-install, controller-generated |
| `MCPJUNGLE_K3S_DEFAULT_ADMIN_TOKEN` | MCPJungle admin token | Issued by app `init-server` — **not yet automated** |
| `MCPJUNGLE_K3S_DEFAULT_CLIENT_TOKEN` | MCP client token | Operator-created via `mcpjungle create mcp-client` |

**Naming hazard (verified, 2026-10-22):** the project holds 174 records across 169
distinct keys, with **5 duplicated keys** (`A2A_PEER_TOKENS`, `AVANTE_GEMINI_API_KEY`,
`ELEVENLABS_API_KEY`, `GITHUB_PAT_FINEGRAINED`, `GITHUB_TOKEN`). The pre-existing
`library/noesis_bws_secret.py::find_secret` returns the **first** match — an
arbitrary-record selection. This role therefore fails closed when a key matches
more than one record instead of picking one.

## 4. Commands

```bash
export PATH=$HOME/.local/bin:$PATH
cd ~/projects/noesis-ansible

# Offline validation (no cluster, no Bitwarden)
python3 tests/mcpjungle_k8s/test_offline.py     # 53 assertions
helm lint charts/mcpjungle
helm template mcpjungle charts/mcpjungle | less

# ansible-playbook --syntax-check needs a vault password, which this host lacks.
# Validate against an isolated tree without the encrypted group_vars:
V=~/.hermes/cache/scratch/ansible-validate
rm -rf $V && mkdir -p $V
cp -a roles playbooks charts library module_utils inventory ansible.cfg $V/
find $V -name secrets.yml -path '*group_vars*' -delete
rm -f $V/ansible.cfg
printf '[defaults]\nroles_path = ./roles\nlibrary = ./library\nmodule_utils = ./module_utils\ninterpreter_python = auto_silent\nnocows = 1\n' > $V/ansible.cfg
cd $V && ansible-playbook --syntax-check -i inventory/mcpjungle-k8s/hosts.ini playbooks/mcpjungle-k8s.yml
ansible-lint --offline playbooks/mcpjungle-k8s.yml

# Preflight / deploy / rollback  -- ALL require explicit approval
ansible-playbook -i inventory/mcpjungle-k8s/hosts.ini playbooks/mcpjungle-k8s.yml --check
ansible-playbook -i inventory/mcpjungle-k8s/hosts.ini playbooks/mcpjungle-k8s.yml --tags k8s,secrets
ansible-playbook -i inventory/mcpjungle-k8s/hosts.ini playbooks/mcpjungle-k8s.yml --tags k8s,expose
```

Tags: `install`, `secrets`, `validate`, `expose`. The `expose` phase is gated on
`mcpjungle_k8s_bw_stored`.

## 5. Uninstall / rollback

```bash
helm uninstall mcpjungle -n mcpjungle --kubeconfig ~/.kube/config --context default
kubectl delete namespace mcpjungle          # retains NOTHING by default
```

**Retained by default (do NOT delete without separate authorization):**
- Bitwarden records — escrow is the durable record; `helm uninstall` does not touch them.
- The PostgreSQL database and its data (external, not owned by this release).
- No operator-managed device is destroyed by removing the Ingress.

**Helm rollback is insufficient** when a GORM `AutoMigrate` has already run against
the database: upstream applies migrations implicitly at every boot with **no
versioned rollback tooling**. A chart rollback restores manifests, not schema.
The same applies to credential rotation — a restored manifest does not un-issue a
token.

## 6. Tailnet exposure

Follows the cluster's established pattern: `networking.k8s.io/v1` Ingress,
`ingressClassName: tailscale`, label `app.kubernetes.io/managed-by: ansible-tailscale-k8s`,
TLS on, host a HOSTSPEC (`mcpjungle`). Tailscale assigns the real name; the role
reads it back from `.status.loadBalancer.ingress[0].hostname` and **fails** if
absent rather than fabricating `*.ts.net`. No Funnel, no public DNS, Service stays
ClusterIP (asserted).

### ⚠ The wildcard ACL defeats per-service restriction

`~/projects/tailscale-lab-acl/policy.hujson` first rule:

```json
{"action": "accept", "src": ["*"], "dst": ["*:*"]}
```

**Every tailnet member can reach every device on every port.** Operator-managed
ingress proxies inherit `operatorConfig.defaultTags = ['tag:k3s']`. Therefore a
new MCPJungle endpoint is reachable by the whole tailnet, and a negative
authorization test **cannot** demonstrate isolation while that rule stands.

Restricting it means narrowing or removing the wildcard — a broad change affecting
every tagged host. **No policy change has been prepared or published.** Restricting
MCPJungle specifically would also require giving it a dedicated tag, which means
changing operator `defaultTags` or moving to a `ProxyClass`/`ProxyGroup` service —
an operator-config change needing approval.

Until then the only real access control on this endpoint is **application-level**:
MCPJungle's static access tokens.

## 7. Blockers and unverified items

1. **Bitwarden write permission UNVERIFIED.** Read access to the project is proven;
   the machine account's *read, write* grant is not. If it is read-only, the first
   escrow write fails. Treat as a provisioning blocker, not a reason to store
   credentials elsewhere.
2. **Admin/client token escrow is not automated.** MCPJungle issues its admin token
   via `init-server` and there is no upstream env var to pre-seed it, so it cannot
   be escrowed before the app runs. A post-install capture phase is still to be
   written. Until then, the deployment creates **no** admin credential, so there is
   nothing unescrowed — but the endpoint would be unusable without a manual token.
3. **`bws secret create` puts the secret VALUE in argv.** Visible in `ps` to local
   users for the process lifetime. Mitigated by `no_log: true` and no shell
   wrappers, but **not eliminated**. The Bitwarden REST API over `uri` would carry
   the value in a request body instead. Not implemented — needs sign-off.
4. **PostgreSQL target not provisioned.** The example points at
   `buzz-postgres-postgresql.buzz.svc.cluster.local`, which is the **Buzz app's**
   instance. Coupling MCPJungle to Buzz's lifecycle is probably wrong. A dedicated
   database is the correct answer and is **not yet created**.
5. **Storage is single-node local-path with `Delete` reclaim.** PVC deletion destroys
   data. Irrelevant in `postgres` mode; critical if switching to SQLite.
6. **Migrations are not reversible.** See §5.
7. **No MCP protocol test has been run.** `validate_k8s.yml` deliberately has its
   port-forward probe disabled (`when: false`). An HTTP 200 on `/health` is **not**
   an MCP integration test; a real `initialize` + `tools/list` exchange over `/mcp`
   through the tailnet endpoint is still required, and must accept an empty tools
   list as valid when no upstreams are registered.
8. **`ansible-playbook --syntax-check` cannot run against the real inventory** —
   `.vault_pass` is absent. Pre-existing and repo-wide. Worked around with the
   isolated tree in §4.
9. **No NetworkPolicy.** The cluster's CNI was not observed to enforce policies, so
   a policy object would be inert and misleading. Deliberately omitted, not forgotten.