<div align="center">
  <img src="noesis-assets/NoesisLab-Agent-Identity/NoesisLab-Logo/NoesisLab-logo-v2.png" width="180" alt="NoesisLab Logo">
  <h1>NoesisPraxis Ansible Stack</h1>
  <p><strong>Infrastructure-as-code for autonomous multi-agent systems</strong></p>

  [![Ansible](https://img.shields.io/badge/Ansible-EE0000?logo=ansible&logoColor=white)](https://www.ansible.com/)
  [![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
  [![Tailscale](https://img.shields.io/badge/Tailscale-000000?logo=tailscale&logoColor=white)](https://tailscale.com/)
  [![macOS](https://img.shields.io/badge/macOS-000000?logo=apple&logoColor=white)](https://www.apple.com/macos/)
  [![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
  [![Status](https://img.shields.io/badge/Status-Active-success.svg)]()

  <p>
    <a href="#quick-start">Quick Start</a> •
    <a href="#stack-components">Stack</a> •
    <a href="#repository-layout">Layout</a> •
    <a href="#security-and-secrets">Security</a> •
    <a href="#mac-specific-notes">macOS</a>
  </p>
</div>

---

## Purpose

This repository is the **single source of truth** for deploying, maintaining, and operating the NoesisPraxis agent stack. It manages registries, security boundaries, agent runtimes, macOS services, and communications through idempotent Ansible playbooks and roles.

> Designed for local-first, home-lab operation with production-ready expansion paths.

## Stack Components

| Component | Purpose | Status |
|-----------|---------|--------|
| **ACP Registry** | Agent-client protocol registry and lifecycle tracking | Scaffold |
| **ANS** | Agent Name Service — secure naming, discovery, certificates | Scaffold |
| **Agent Registry** | Centralized governance dashboard for agents, skills, MCPs | Scaffold |
| **A2A Registry** | Live A2A agent discovery and Agent Card management | Scaffold |
| **MCPJungle** | MCP server registry and approved tool gateway | Scaffold |
| **Clawvisor** | Security layer — policy, identity, sandboxing, access control | Scaffold |
| **Telegram** | Human-in-the-loop group chat communications | Scaffold |
| **OpenClaw** | Generic Dockerized agent runtime | Scaffold |
| **Hermes** | Generic Dockerized supervisor/assistant runtime | Scaffold |
| **macOS ClawDev** | Lightweight OpenClaw for Apple Silicon | Scaffold |
| **macOS HermesDev** | Local Hermes supervisor for Apple Silicon | Scaffold |
| **Tailscale** | Secure mesh networking for remote management | Scaffold |

## Quick Start

```bash
# Bootstrap the control node
ansible-playbook -i inventory/local/hosts.ini playbooks/bootstrap.yml

# Deploy full stack (local)
ansible-playbook -i inventory/local/hosts.ini playbooks/site.yml

# Run specific phases
ansible-playbook -i inventory/local/hosts.ini playbooks/master-stack.yml --tags foundation,security

# Validate health
ansible-playbook -i inventory/local/hosts.ini playbooks/validate.yml

# macOS agents over Tailscale
ansible-playbook -i inventory/tailscale/hosts.ini playbooks/macos-clawdev.yml
ansible-playbook -i inventory/tailscale/hosts.ini playbooks/macos-hermesdev.yml
```

## Repository Layout

```
.
├── inventory/          # local, tailscale, production inventories
├── playbooks/          # Layer-specific and orchestration playbooks
├── roles/              # 14 reusable roles per stack component
├── group_vars/         # Shared group variables
├── host_vars/          # Per-host variables
├── templates/          # Global templates (common, registries, macos, security)
├── files/              # Static files (JSON schemas, helper scripts)
└── scripts/            # Operational helper scripts
```

## Orchestration Flow

```
PHASE 0  Bootstrap        → Host prep, secrets, preflight
PHASE 1  Foundation       → ACP, ANS, Agent Registry, A2A registries
PHASE 2  Security         → MCPJungle, Clawvisor policies and ACLs
PHASE 3  Runtime          → Dockerized OpenClaw and Hermes deployments
PHASE 4  macOS            → launchd services, resource budgets, Tailscale exposure
PHASE 5  Communications   → Telegram bot provisioning and group integration
PHASE 6  Networking       → Tailscale mesh, remote management wiring
PHASE 7  Sync & Backup    → Cross-registry sync, backup, restore hooks
PHASE 8  Validation       → Health checks, schema validation, connectivity tests
```

## Inventory and Environments

| Inventory | Use Case | Connection |
|-----------|----------|------------|
| `inventory/local/` | Local development and Dockerized services | `local` |
| `inventory/tailscale/` | Remote macOS management over Tailscale | SSH over tailnet |
| `inventory/production/` | Production deployment targets | SSH |

```bash
# Select environment
ansible-playbook -i inventory/local/hosts.ini       playbooks/site.yml
ansible-playbook -i inventory/tailscale/hosts.ini   playbooks/site.yml
ansible-playbook -i inventory/production/hosts.ini  playbooks/site.yml
```

## Security and Secrets

- **Vault-encrypted** — Secrets live in `group_vars/secrets.yml` and `inventory/*/group_vars/secrets.yml`
- **Zero hardcoded credentials** — No tokens, keys, or passwords in templates or playbooks
- **Least-privilege** — Default-deny Clawvisor policies, scoped MCP tool access
- **Local-first** — No broad network exposure; localhost and tailnet only

## macOS Specific Notes

- Agents run as **per-user `launchd`** services with generated plists
- **Conservative resource budgets** — suitable for MacBook Pro M1 Pro with 16 GB RAM
  - ClawDev: 50% CPU cap, 512 MB RAM
  - HermesDev: 50% CPU cap, 1024 MB RAM
- Services bind to `localhost` and are reachable over the **Tailscale tailnet**
- All state lives in **user-space paths**:
  - Config: `~/.config/noesis/`
  - Logs: `~/.local/share/noesis/`
  - Plists: `~/Library/LaunchAgents/`

## Operational Scripts

| Script | Purpose |
|--------|---------|
| `scripts/bootstrap.sh` | Initial host preparation |
| `scripts/validate.sh` | Stack health and schema validation |
| `scripts/backup.sh` | Registry and config backup |
| `scripts/restore.sh` | Registry and config restore |
| `scripts/sync-registries.sh` | Cross-registry synchronization |

## Maintenance

```bash
# Rolling maintenance window
ansible-playbook -i inventory/local/hosts.ini playbooks/maintenance.yml

# Controlled rollback
ansible-playbook -i inventory/local/hosts.ini playbooks/rollback.yml

# Registry backup
ansible-playbook -i inventory/local/hosts.ini playbooks/backup.yml
```

---

<div align="center">
  <sub>Built with discipline. No hype. No exceptions.</sub>
</div>
