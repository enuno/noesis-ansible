# NoesisPraxis Ansible Stack

Ansible-driven infrastructure for the NoesisPraxis multi-agent system.

## Purpose

This repository is the single source of truth for deploying, maintaining, and operating the NoesisPraxis agent stack. It manages registries, security boundaries, agent runtimes, macOS services, and communications through idempotent Ansible playbooks and roles.

## Stack Components

| Component | Purpose |
|-----------|---------|
| ACP Registry | Agent-client protocol registry and lifecycle tracking |
| ANS | Agent Name Service — secure naming, discovery, certificates |
| Agent Registry | Centralized governance dashboard for agents, skills, MCPs |
| A2A Registry | Live A2A agent discovery and Agent Card management |
| MCPJungle | MCP server registry and approved tool gateway |
| Clawvisor | Security layer — policy, identity, sandboxing, access control |
| Telegram | Human-in-the-loop group chat communications |
| OpenClaw | Generic Dockerized agent runtime |
| Hermes | Generic Dockerized supervisor/assistant runtime |
| macOS ClawDev | Lightweight OpenClaw for Apple Silicon |
| macOS HermesDev | Local Hermes supervisor for Apple Silicon |
| Tailscale | Secure mesh networking for remote management |

## Repository Layout

```
ansible/
├── inventory/          # local, tailscale, production inventories
├── playbooks/          # Layer-specific and orchestration playbooks
├── roles/              # Reusable roles per stack component
├── group_vars/         # Shared group variables
├── host_vars/          # Per-host variables
├── templates/          # Global templates (common, registries, macos, security)
├── files/              # Static files (JSON schemas, helper scripts)
└── scripts/            # Operational helper scripts
```

## Orchestration Flow

1. **Bootstrap** — Host preparation and directory setup
2. **Foundation** — ACP, ANS, Agent Registry, A2A registries
3. **Security** — MCPJungle, Clawvisor policies and access controls
4. **Runtime** — Dockerized OpenClaw and Hermes deployments
5. **macOS / Tailscale** — launchd services, resource budgets, mesh networking
6. **Communications** — Telegram bot provisioning and group integration
7. **Validation** — Health checks, schema validation, connectivity tests
8. **Maintenance** — Backup, restore, rollback, registry sync

## How to Run

```bash
# Full stack (local)
ansible-playbook -i inventory/local/hosts.ini playbooks/site.yml

# Master orchestrator with tags
ansible-playbook -i inventory/local/hosts.ini playbooks/master-stack.yml --tags foundation,security

# Validate only
ansible-playbook -i inventory/local/hosts.ini playbooks/validate.yml

# macOS agents via Tailscale
ansible-playbook -i inventory/tailscale/hosts.ini playbooks/macos-clawdev.yml
ansible-playbook -i inventory/tailscale/hosts.ini playbooks/macos-hermesdev.yml
```

## Inventory and Environments

| Inventory | Use Case |
|-----------|----------|
| `inventory/local/` | Local development and Dockerized services |
| `inventory/tailscale/` | Remote macOS management over Tailscale |
| `inventory/production/` | Production deployment targets |

Select inventory with `-i inventory/<name>/hosts.ini`.

## Security and Secrets

- Secrets live in vault-encrypted files (`group_vars/secrets.yml`, `inventory/*/group_vars/secrets.yml`).
- No hardcoded credentials in templates, playbooks, or inventories.
- Least-privilege defaults. Local-first operation. No broad network exposure.

## Mac-Specific Notes

- Agents run as per-user `launchd` services with generated plists.
- Conservative CPU/RAM budgets suitable for MacBook Pro M1 Pro with 16 GB RAM.
- Services bind to `localhost` and are reachable over the Tailscale tailnet.
- All state lives in user-space paths (`~/.config/noesis/`, `~/.local/share/noesis/`).
