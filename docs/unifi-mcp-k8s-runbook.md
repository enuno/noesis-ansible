# UniFi MCP Project A

Entry point: `playbooks/unifi-mcp.yml` with explicit `-i inventory/praxis-k3s/hosts.ini`; execution is controller-local. No BWS or cluster changes occur without `unifi_mcp_enabled=true` and `unifi_mcp_allow_apply=true`. `unifi_mcp_allow_bws_create` is a separate creation opt-in. Supply `BWS_ACCESS_TOKEN` in the controller environment and `unifi_mcp_organization_id=93331de5-fa6e-44ab-8aee-b3840034e681`; the token must never appear in `-e` or argv. No records are overwritten: resolver reuses, fails on ambiguous names, and only generates missing scoped records with explicit approval. Required SDK and Kubernetes Python dependencies are in `roles/unifi_mcp/requirements-controller.txt`.

Four selector values:

- `docker_single`: pinned `ghcr.io/enuno/unifi-mcp-server:0.7.0-fleet`, one loopback-only Docker container; local controller, read-only MCP. No fleet database.
- `compose_fleet`: upstream `docker-compose.fleet.yml` plus the role's Compose overlay; one server and worker, authenticated Redis, migrations as schema owner followed by runtime-role grants.
- `compose_fleet_scale`: upstream fleet and scale Compose files plus the same overlay; three servers, two workers, sticky nginx, authenticated Redis.
- `kubernetes_helm`: pinned upstream chart 0.1.5, app 0.7.0, external Postgres/Redis; separate application, database-owner, and Redis-auth Secrets. An Ansible-managed Job migrates as owner then grants the runtime role before Helm creates servers or worker. Upstream chart migration hook is disabled (`fleet.migrate=false`) because its `envFrom` would expose the owner URL to every app pod. The schema Job is recreated on each approved apply to rerun migrations and grants. Helm still owns the application workload; it does not own the Postgres/Redis PVCs.

The upstream Compose fleet file contains literal `:***@postgres` placeholders. **Never run it alone**. The role overrides all three DATABASE_URL values, replaces build with pinned image, and gates start on migration and runtime grants. Compose interpolation requires Docker Compose with `!reset` support (verified with v5.6.1). Secrets are passed in the local Compose process environment, not command-line arguments or a generated `.env`; Docker itself stores container environment, so restrict host/Docker access. The non-secret SQL is written mode 0600 under `unifi_mcp_compose_dir`. Each mode is an alternative for a separately managed install, not a migration mechanism; switching modes does not transfer database or audit history.

Kubernetes setup requires absolute `unifi_mcp_kubeconfig` and explicit `unifi_mcp_context`, checked against the file; no ambient context is accepted. The chart and Compose definitions are checked against pinned upstream revision `6e478142bf5fcdb76a22c5ac8ed29040fe7c8ce5` (v0.7.0). Configure backups for local-path Postgres PVC and audit retention before production; the data tier is single-node/non-HA. Application runtime role can read/write operational tables, append audit rows, but cannot modify or delete audit rows or create schema. Generated owner and runtime passwords must be distinct. `UNIFI_CLOUD_API_KEY` is intentionally not included in the app Secret; cloud access is independently tested and is not part of the local-controller runtime.

```bash
# Static parse; check mode does not resolve BWS or write to Kubernetes.
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/unifi-mcp.yml --syntax-check
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/unifi-mcp.yml --check -e unifi_mcp_enabled=true -e unifi_mcp_mode=kubernetes_helm -e unifi_mcp_kubeconfig=/absolute/path -e unifi_mcp_context=default
# After approval only: add -e unifi_mcp_allow_apply=true, -e unifi_mcp_organization_id=<verified UUID>, and, only if missing records are to be generated, -e unifi_mcp_allow_bws_create=true.
```

Exposure is a separate opt-in (`unifi_mcp_allow_expose=true`), Kubernetes only, via Tailscale IngressClass `unifi-mcp-server`. Verify live job completion, role privileges, release status, pods, `/healthz`, operator proxy and actual MCP endpoint before calling it live. Rollback the application with Helm, preserve PVCs and BWS records; schema migrations are not automatically reversible. Compose/Docker expose only loopback, not a tailnet FQDN.
