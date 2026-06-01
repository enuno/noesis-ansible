# NoesisPraxis Ansible Stack

This repository contains the Ansible automation for the NoesisPraxis multi-agent system. It is the source of truth for deploying, configuring, validating, and maintaining the registry, security, communications, and agent runtime layers that support NoesisPraxis and its related agents.

The stack is designed to be modular, local-first, and reproducible. It includes registry services, identity services, MCP tooling, security policy enforcement, Telegram communications, generic OpenClaw/Hermes runtime deployments, and macOS-specific agents for a MacBook Pro M1 Pro environment.

## What this repo manages

- ACP registry for agent lifecycle and discovery.
- ANS for secure agent naming and resolution.
- Agent Registry dashboard for centralized management.
- A2A registry for live agent cards and discovery.
- MCPJungle for MCP server registration and approved tool access.
- Clawvisor for policy, isolation, and security enforcement.
- Telegram integration for human-in-the-loop communications.
- OpenClaw and Hermes runtime deployments.
- Noesis ClawDev and Noesis HermesDev on macOS.
- Tailscale-based remote management and agent connectivity.
- Backup, restore, validation, rollback, and registry synchronization.

## Repository layout

- `inventory/` — environment-specific inventories for local, Tailscale, and production use.
- `playbooks/` — top-level orchestration entry points for bootstrap, stack deployment, validation, maintenance, and rollback.
- `roles/` — reusable Ansible roles for each subsystem and runtime.
- `templates/` — shared Jinja2 templates for configs, registry entries, launchd plists, and security policies.
- `files/` — JSON schemas, validation helpers, and utility scripts.
- `scripts/` — convenience scripts for bootstrap, backup, restore, validation, and registry sync.
- `README.md` — this document.

## How it works

The playbooks are organized to run in phases:

1. Bootstrap the environment.
2. Deploy identity and registry foundations.
3. Configure security and access control.
4. Deploy agent runtimes.
5. Bring up macOS-specific services.
6. Enable Tailscale connectivity.
7. Register and synchronize Telegram communications.
8. Validate health, connectivity, and schema compliance.
9. Back up or roll back state when needed.

`playbooks/site.yml` is the normal operator entry point. `playbooks/master-stack.yml` is the phase-oriented orchestrator that can be run in full or by tag.

## Getting started

### Prerequisites

- Ansible installed on the control machine.
- Access to the target host(s) via SSH or Tailscale.
- Required secrets stored in Ansible Vault or another secure secret backend.
- Any external services or registries available before their dependent roles are run.

### Typical commands

Run the default site playbook:

```bash
ansible-playbook playbooks/site.yml
```

Run the full master stack:

```bash
ansible-playbook playbooks/master-stack.yml
```

Run validation only:

```bash
ansible-playbook playbooks/validate.yml
```

Run in check mode:

```bash
ansible-playbook --check playbooks/site.yml
```

Show tasks only:

```bash
ansible-playbook playbooks/site.yml --list-tasks
```

## Inventories

- `inventory/local/` — local bootstrap and home-lab testing.
- `inventory/tailscale/` — remote management over the tailnet.
- `inventory/production/` — production-ready expansion point.

Use the local inventory for first-time development and the Tailscale inventory when managing the MacBook Pro remotely.

## Security and secrets

- Do not hardcode tokens, passwords, or certificates in templates or inventories.
- Store secrets in Ansible Vault or a comparable protected secret store.
- Keep default access scoped to least privilege.
- Prefer local-first and tailnet-only exposure over public network access.

## Mac-specific notes

The macOS deployment targets a MacBook Pro M1 Pro with 16 GB RAM. The Mac-specific roles use `launchd`-managed services, conservative CPU and memory budgets, and explicit localhost plus Tailscale exposure where required. The goal is to keep the system lightweight and manageable on Apple Silicon while still supporting direct interaction and delegated work.

## Maintenance

The repo includes playbooks and roles for:

- Backup and restore.
- Validation and health checks.
- Registry synchronization.
- Maintenance mode and controlled restarts.
- Rollback paths for safe change management.

## Extending the stack

The repository is organized so new agents, registries, or tool services can be added by creating a new role, template set, and playbook entry without restructuring the existing stack. The file and role layout is intentionally explicit to keep orchestration readable and auditable.

## Notes

This project treats Ansible as the deployment and configuration source of truth. Each playbook should remain idempotent, and each role should be safe to rerun.
