# CLAUDE.md — NoesisPraxis Ansible Stack

## Project Identity

NoesisPraxis infrastructure automation. Ansible-driven deployment of a multi-agent stack with registries, security, runtimes, and communications. Local-first, home-lab ready, production-expandable.

## Architecture

```
Human (Operator/Telegram)
    |
Tailscale Mesh VPN
    |
+-----------+-----------+-----------+
|           |           |           |
Control   Security   Runtime    macOS
8081-8084  8085      8090-8091  launchd
ACP ANS   MCPJungle  OpenClaw   ClawDev 512MB
AgentReg  Clawvisor  Hermes     HermesDev 1024MB
A2A
```

## Stack Phases

| Phase | Tag | What |
|-------|-----|------|
| 0 | bootstrap | Host prep, dirs, secrets load |
| 1 | foundation | ACP, ANS, Agent Registry, A2A |
| 2 | security | MCPJungle, Clawvisor policies |
| 3 | runtime | Dockerized OpenClaw, Hermes |
| 4 | macos | launchd, resource budgets, tailnet |
| 5 | communications | Telegram bot, group integration |
| 6 | networking | Tailscale mesh, remote wiring |
| 7 | sync,backup | Cross-registry sync, backup/restore |
| 8 | validate | Health, schema, connectivity tests |

## Critical Constraints

1. **No secrets in repo** — Vault-encrypted `secrets.yml` only; templates are clean
2. **Ansible-core 2.13+** — No deprecated keys; `result_format = yaml`, not `bin_ansible_callbacks`
3. **Idempotent everything** — Re-runnable roles; handlers for service restarts
4. **macOS resource caps** — ClawDev 512MB RAM / 50% CPU; HermesDev 1024MB RAM / 50% CPU
5. **Local-first** — Default inventory is `inventory/local/hosts.ini`; tailscale is opt-in

## Code Patterns

### Role structure
```yaml
# roles/<name>/tasks/main.yml
- include_tasks: install.yml
- include_tasks: configure.yml
- include_tasks: validate.yml
```

### Toggle-gated inclusion
```yaml
# playbooks/master-stack.yml
vars:
  _enable_acp: "{{ noesispraxis_enable_acp | default(true) | bool }}"
tasks:
  - include_role: name=acp_registry
    when: _enable_acp
```

### macOS launchd plist template
```jinja2
# templates/macos/com.noesis.<name>.plist.j2
<key>ProcessType</key><string>Background</string>
<key>Nice</key><integer>10</integer>
```

### Validation hook
```yaml
# Every phase ends with:
- include_role: name=validation
  when: noesispraxis_enable_validation | default(true) | bool
```

## File Conventions

| Extension | Purpose |
|-----------|---------|
| `.yml` | Playbooks, roles, vars |
| `.j2` | Jinja2 templates (docker-compose, plists, configs) |
| `.json` | Schemas, agent cards, registry entries |
| `.ini` | Inventory hosts |
| `.sh` | Operational scripts (bootstrap, validate, backup) |

## Testing Checklist

Before committing:
- [ ] `ansible-playbook --syntax-check` on all playbooks
- [ ] `ansible-playbook --check` on bootstrap + target playbook
- [ ] JSON schemas validate with `scripts/validate-json.sh`
- [ ] YAML lint: no trailing spaces, consistent indentation
- [ ] No secrets in diff: `git diff --check` + manual review

## Common Pitfalls

- **Inventory mismatch** — `local` vs `tailscale` vs `production`; host_vars differ
- **Secret not loaded** — `secrets_loaded` must be set or vault file ignored silently
- **macOS path assumptions** — Use `ansible_env.HOME`, not `~`; `ansible_user_id` for user
- **Docker not running** — Check `docker info` before compose tasks
- **Tailscale auth** — `tailscale_auth_key` empty string means skip; must be set for join

## Extension Points

- **New registry** — Add role, defaults, templates; wire into Phase 1
- **New agent runtime** — Mirror `openclaw/` or `hermes/`; add playbook
- **New security policy** — Update `templates/security/clawvisor-policy.yml.j2`
- **New inventory** — Create `inventory/<name>/`, add to `ansible.cfg` if default
- **New validation** — Add task file in `roles/validation/tasks/`

## Dependencies

- ansible-core >= 2.13
- collections: `community.docker`, `community.general`
- Docker Engine + Compose plugin (runtime hosts)
- Tailscale (remote management)
- macOS: `launchctl`, `plutil` (plist validation)
