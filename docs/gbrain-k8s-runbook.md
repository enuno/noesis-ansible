# GBrain on k3s (Helm + Tailscale MCP + Supabase)

Prepared playbook. Not deployed until you approve a live run.

## What this is

GBrain (`garrytan/gbrain`, checkout `~/tools/gbrain`, VERSION `0.60.747.0`) as
an HTTP MCP server on the praxis k3s cluster.

- Chart: in-repo `charts/gbrain` (upstream has no official chart or production image)
- Image: built from `~/tools/gbrain` with `charts/gbrain/docker/Dockerfile`
- Engine: **Supabase Postgres**, not PGLite and not an in-cluster database
- MCP: `gbrain serve --http --port 3131 --bind 0.0.0.0 --public-url https://gbrain.<tailnet>.ts.net`
- Exposure: Tailscale operator Ingress (`ingressClassName: tailscale`), same shape as MCPJungle

`gbrain mcp expose` is the host Tailscale Serve path. This cluster publishes
Services with operator Ingress instead.

## Commands (offline first)

```bash
ansible-playbook -i inventory/gbrain-k8s/hosts.ini playbooks/gbrain-k8s.yml --syntax-check
ansible-playbook -i inventory/gbrain-k8s/hosts.ini playbooks/gbrain-k8s.yml --check
python3 tests/gbrain_k8s/test_offline.py
```

Live apply (separate approval):

```bash
ansible-playbook -i inventory/gbrain-k8s/hosts.ini playbooks/gbrain-k8s.yml
ansible-playbook -i inventory/gbrain-k8s/hosts.ini playbooks/gbrain-k8s.yml \
  -e gbrain_k8s_expose_enabled=true
```

After the operator mints a proxy, sign it from this Tailnet Lock signing node
if `tailscale lock status --json` lists it under FilteredPeers.

## Supabase (you create; Ansible does not)

1. Create a Supabase project.
2. Escrow in Bitwarden SM project `72974d0e-81af-4678-bab7-b46000985859`:
   - `GBRAIN_K3S_DATABASE_URL` — transaction pooler (port 6543)
   - `GBRAIN_K3S_DIRECT_DATABASE_URL` — session pooler (port 5432, IPv4). Direct
     `db.<ref>.supabase.co:5432` is IPv6-only and will fail from this cluster
     unless the IPv4 add-on is on (see gbrain `docs/GBRAIN_VERIFY.md`).
3. Optional: `GBRAIN_K3S_ADMIN_BOOTSTRAP_TOKEN`
4. Enable `pgvector` on the project.

Pass-through for a single run (still not committed):

```bash
-e gbrain_k8s_database_url='postgresql://...' \
-e gbrain_k8s_direct_database_url='postgresql://...'
```

The Kubernetes Secret is created only when both extra-vars are non-empty.
Bitwarden list is used to confirm records exist.

## Client MCP URL

Use the operator-assigned HTTPS hostname:

`https://gbrain.<tailnet>.ts.net/mcp`

Never `http://`, never the tailnet IP, never the Service port on the tailnet.
`/health` is liveness-only. Prove MCP with a real `/mcp` client call.

New proxy devices start locked out under Tailnet Lock until signed here.

## Not done by this play

- Creating or migrating a Supabase project
- `gbrain mcp expose` / Funnel / public DNS
- Wiring into `playbooks/master-stack.yml`
- A live deploy
