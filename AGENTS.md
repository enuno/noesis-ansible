# AGENTS.md — NoesisPraxis Ansible Stack

## What This Repo Is

Infrastructure-as-code for the NoesisPraxis multi-agent system. Ansible playbooks and roles deploy registries, security boundaries, agent runtimes, macOS services, and communications. Single source of truth. Local-first. Production-ready expansion path.

## Quick Context

| Layer | Components | Ports |
|-------|-----------|-------|
| Control | ACP Registry, ANS, Agent Registry, A2A Registry | 8081-8084 |
| Security | MCPJungle, Clawvisor | 8085 |
| Runtime | OpenClaw, Hermes | 8090-8091 |
| macOS | ClawDev (512MB), HermesDev (1024MB) | localhost |
| Network | Tailscale mesh VPN | — |
| Comms | Telegram bot | — |

## Entry Points

```bash
# Full stack
ansible-playbook -i inventory/local/hosts.ini playbooks/site.yml

# Phase-filtered
ansible-playbook -i inventory/local/hosts.ini playbooks/master-stack.yml --tags foundation,security

# Single component
ansible-playbook -i inventory/local/hosts.ini playbooks/acp-registry.yml

# macOS over Tailscale
ansible-playbook -i inventory/tailscale/hosts.ini playbooks/macos-clawdev.yml
```

## Key Design Decisions

- **Idempotent roles** — install/configure/validate pattern; safe to re-run
- **Phase-gated** — master-stack.yml runs 0-8; skip via `--tags`
- **Toggle-driven** — `noesispraxis_enable_*` vars in `group_vars/all.yml`
- **Secret-free templates** — vault files only; no hardcoded credentials
- **macOS-native** — launchd plists, user-space paths, conservative RAM/CPU caps
- **Tailscale-first** — remote management over tailnet; localhost for local

## File Map

```
playbooks/site.yml          # Operator entry point
playbooks/master-stack.yml  # Phase orchestrator (0-8)
playbooks/bootstrap.yml     # Host prep
playbooks/validate.yml      # Health + schema + connectivity
inventory/local/            # Local dev (localhost)
inventory/tailscale/        # Remote macOS (tailnet)
inventory/production/       # Production targets
roles/                      # 14 roles, one per component
templates/                  # Shared: docker-compose, launchd, policies
files/schemas/              # JSON schemas for validation
scripts/                    # Operational helpers
```

## Agent Context Rules

1. **Never hardcode secrets** — use `inventory/*/group_vars/secrets.yml` (vault-encrypted)
2. **Always validate** — run `ansible-playbook --syntax-check` before committing
3. **Prefer check mode** — `ansible-playbook --check` for dry-run verification
4. **macOS assumptions** — `ansible_user_id`, `ansible_env.HOME`, `launchctl`
5. **Docker assumptions** — `community.docker` collection; compose v2
6. **Idempotency** — roles must be safely re-runnable; handlers for restarts

## Common Tasks

| Task | Command |
|------|---------|
| Syntax-check all | `find playbooks -name '*.yml' -exec ansible-playbook --syntax-check -i inventory/local/hosts.ini {} \;` |
| Check-mode bootstrap | `ansible-playbook --check -i inventory/local/hosts.ini playbooks/bootstrap.yml` |
| Validate stack | `ansible-playbook -i inventory/local/hosts.ini playbooks/validate.yml` |
| Backup | `ansible-playbook -i inventory/local/hosts.ini playbooks/backup.yml` |
| Rollback | `ansible-playbook -i inventory/local/hosts.ini playbooks/rollback.yml` |

## When Modifying

- **New role?** Mirror existing: `defaults/`, `handlers/`, `tasks/{install,configure,validate}.yml`
- **New playbook?** Add to `playbooks/` and wire into `master-stack.yml` with tags
- **New inventory?** Create under `inventory/<name>/` with `hosts.ini`, `group_vars/all.yml`
- **Schema changes?** Update `files/schemas/` and `roles/validation/tasks/schema.yml`
- **Policy changes?** Update `templates/security/clawvisor-policy.yml.j2`

## Dependencies

- ansible-core 2.13+
- collections: `community.docker`, `community.general`
- Docker + compose (runtime hosts)
- Tailscale (remote hosts)
- macOS: `launchctl`, `plutil` (for plist validation)
