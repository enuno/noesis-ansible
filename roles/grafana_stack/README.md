# Grafana Stack Role

Ansible role that deploys the Grafana observability stack integrated from `~/tools/railway-grafana-stack` into the NoesisPraxis infrastructure.

## Services

| Service | Image | Host Port | Purpose |
|---------|-------|-----------|---------|
| Grafana | `grafana/grafana-oss` | `3000` | Dashboards and visualization |
| Prometheus | `prom/prometheus` | `9090` | Metrics collection |
| Loki | `grafana/loki` | `3100` | Log aggregation |
| Tempo | `grafana/tempo` | `3200` + `4317`/`4318` | Distributed tracing |

## Quick start

```bash
# Set the Grafana admin password in the vault or via extra var
ansible-vault edit inventory/local/group_vars/secrets.yml
# add: vault_grafana_admin_password: "your-secure-password"

# Enable and deploy
ansible-playbook -i inventory/local/hosts.ini playbooks/grafana-stack.yml \
  -e noesispraxis_enable_grafana_stack=true
```

## Configuration

All tunables live in `roles/grafana_stack/defaults/main.yml`. Override in `group_vars/all.yml`, `host_vars/`, or via `-e`.

Key variables:

- `noesispraxis_enable_grafana_stack` — master toggle (`false` by default)
- `grafana_stack_admin_password` — required; defaults to `vault_grafana_admin_password`
- `grafana_stack_grafana_version`, `grafana_stack_prometheus_version`, etc. — pinned image tags
- `grafana_stack_prometheus_retention_time` — Prometheus TSDB retention

## Secrets

The Grafana admin password is never stored in plain text in this role. Provide it via:

1. Bitwarden Secrets Manager (add `GRAFANA_ADMIN_PASSWORD` → `vault_grafana_admin_password` in `group_vars/all.yml` `bitwarden_secrets_map`)
2. `ansible-vault` encrypted `group_vars/secrets.yml`
3. Extra variable: `-e grafana_stack_admin_password=...`

## Validation

The role waits for and checks the health endpoints of all enabled services after deployment.

## Source

Derived from the Railway template in `~/tools/railway-grafana-stack`, converted from custom Dockerfiles to official images with configuration mounted via Ansible templates.
