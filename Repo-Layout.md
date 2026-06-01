Below is a repository-ready **master task tree** for the Ansible repo. It turns the full NoesisPraxis stack into a clean build order with exact directory names and file names, including ACP, ANS, Agent Registry, A2A, MCPJungle, Clawvisor, Telegram, OpenClaw/Hermes runtimes, and the macOS + Tailscale path.

## Repo layout

```text
ansible/
├── README.md
├── ansible.cfg
├── requirements.yml
├── inventory/
│   ├── local/
│   │   ├── hosts.ini
│   │   ├── group_vars/
│   │   │   ├── all.yml
│   │   │   └── secrets.yml
│   │   └── host_vars/
│   │       ├── localhost.yml
│   │       └── macbook-pro-m1pro.yml
│   ├── tailscale/
│   │   ├── hosts.ini
│   │   ├── group_vars/
│   │   │   └── all.yml
│   │   └── host_vars/
│   │       └── macbook-pro-m1pro.yml
│   └── production/
│       ├── hosts.ini
│       └── group_vars/
│           └── all.yml
├── playbooks/
│   ├── site.yml
│   ├── bootstrap.yml
│   ├── backup.yml
│   ├── restore.yml
│   ├── validate.yml
│   ├── maintenance.yml
│   ├── rollback.yml
│   ├── acp-registry.yml
│   ├── ans.yml
│   ├── agentregistry.yml
│   ├── a2a-registry.yml
│   ├── mcpjungle.yml
│   ├── clawvisor.yml
│   ├── telegram.yml
│   ├── openclaw.yml
│   ├── hermes.yml
│   ├── macos-clawdev.yml
│   ├── macos-hermesdev.yml
│   ├── tailscale.yml
│   └── master-stack.yml
├── roles/
│   ├── acp_registry/
│   │   ├── defaults/main.yml
│   │   ├── handlers/main.yml
│   │   ├── tasks/main.yml
│   │   ├── tasks/install.yml
│   │   ├── tasks/configure.yml
│   │   ├── tasks/register.yml
│   │   ├── tasks/validate.yml
│   │   ├── tasks/backup.yml
│   │   ├── templates/registry.json.j2
│   │   ├── templates/docker-compose.yml.j2
│   │   └── templates/env.j2
│   ├── ans/
│   │   ├── defaults/main.yml
│   │   ├── handlers/main.yml
│   │   ├── tasks/main.yml
│   │   ├── tasks/install.yml
│   │   ├── tasks/configure.yml
│   │   ├── tasks/register.yml
│   │   ├── tasks/validate.yml
│   │   ├── templates/ans-config.yml.j2
│   │   ├── templates/ans-agent-card.json.j2
│   │   └── templates/docker-compose.yml.j2
│   ├── agentregistry/
│   │   ├── defaults/main.yml
│   │   ├── handlers/main.yml
│   │   ├── tasks/main.yml
│   │   ├── tasks/install.yml
│   │   ├── tasks/configure.yml
│   │   ├── tasks/dashboard.yml
│   │   ├── tasks/validate.yml
│   │   ├── templates/registry-dashboard.yml.j2
│   │   ├── templates/agents.yml.j2
│   │   └── templates/docker-compose.yml.j2
│   ├── a2a_registry/
│   │   ├── defaults/main.yml
│   │   ├── handlers/main.yml
│   │   ├── tasks/main.yml
│   │   ├── tasks/install.yml
│   │   ├── tasks/configure.yml
│   │   ├── tasks/onboard.yml
│   │   ├── tasks/validate.yml
│   │   ├── tasks/backup.yml
│   │   ├── templates/a2a-registry-config.yml.j2
│   │   ├── templates/agent-card.json.j2
│   │   ├── templates/registry-agent.json.j2
│   │   └── templates/docker-compose.yml.j2
│   ├── mcpjungle/
│   │   ├── defaults/main.yml
│   │   ├── handlers/main.yml
│   │   ├── tasks/main.yml
│   │   ├── tasks/install.yml
│   │   ├── tasks/configure.yml
│   │   ├── tasks/onboard.yml
│   │   ├── tasks/validate.yml
│   │   ├── tasks/backup.yml
│   │   ├── templates/mcpjungle-config.yml.j2
│   │   ├── templates/mcp-server.json.j2
│   │   └── templates/docker-compose.yml.j2
│   ├── clawvisor/
│   │   ├── defaults/main.yml
│   │   ├── handlers/main.yml
│   │   ├── tasks/main.yml
│   │   ├── tasks/install.yml
│   │   ├── tasks/configure.yml
│   │   ├── tasks/policy.yml
│   │   ├── tasks/validate.yml
│   │   └── templates/clawvisor-policy.yml.j2
│   ├── telegram/
│   │   ├── defaults/main.yml
│   │   ├── handlers/main.yml
│   │   ├── tasks/main.yml
│   │   ├── tasks/install.yml
│   │   ├── tasks/configure.yml
│   │   ├── tasks/webhook.yml
│   │   ├── tasks/polling.yml
│   │   ├── tasks/groupchat.yml
│   │   ├── tasks/register.yml
│   │   ├── tasks/validate.yml
│   │   ├── templates/telegram-bot.env.j2
│   │   ├── templates/telegram-bot.yml.j2
│   │   └── templates/agent-telegram.json.j2
│   ├── openclaw/
│   │   ├── defaults/main.yml
│   │   ├── handlers/main.yml
│   │   ├── tasks/main.yml
│   │   ├── tasks/install.yml
│   │   ├── tasks/configure.yml
│   │   ├── tasks/launchd.yml
│   │   ├── tasks/docker.yml
│   │   ├── tasks/validate.yml
│   │   └── templates/openclaw-config.json.j2
│   ├── hermes/
│   │   ├── defaults/main.yml
│   │   ├── handlers/main.yml
│   │   ├── tasks/main.yml
│   │   ├── tasks/install.yml
│   │   ├── tasks/configure.yml
│   │   ├── tasks/launchd.yml
│   │   ├── tasks/docker.yml
│   │   ├── tasks/validate.yml
│   │   └── templates/hermes-config.json.j2
│   ├── macos_clawdev/
│   │   ├── defaults/main.yml
│   │   ├── handlers/main.yml
│   │   ├── tasks/main.yml
│   │   ├── tasks/install.yml
│   │   ├── tasks/configure.yml
│   │   ├── tasks/launchd.yml
│   │   ├── tasks/network.yml
│   │   ├── tasks/validate.yml
│   │   ├── templates/com.noesis.clawdev.plist.j2
│   │   ├── templates/openclaw-config.json.j2
│   │   └── templates/resource-budget.yml.j2
│   ├── macos_hermesdev/
│   │   ├── defaults/main.yml
│   │   ├── handlers/main.yml
│   │   ├── tasks/main.yml
│   │   ├── tasks/install.yml
│   │   ├── tasks/configure.yml
│   │   ├── tasks/launchd.yml
│   │   ├── tasks/network.yml
│   │   ├── tasks/validate.yml
│   │   ├── templates/com.noesis.hermesdev.plist.j2
│   │   ├── templates/hermes-config.json.j2
│   │   └── templates/resource-budget.yml.j2
│   ├── tailscale/
│   │   ├── defaults/main.yml
│   │   ├── handlers/main.yml
│   │   ├── tasks/main.yml
│   │   ├── tasks/install.yml
│   │   ├── tasks/configure.yml
│   │   ├── tasks/validate.yml
│   │   └── templates/tailscale-network.yml.j2
│   ├── backup/
│   │   ├── defaults/main.yml
│   │   ├── handlers/main.yml
│   │   ├── tasks/main.yml
│   │   ├── tasks/backup.yml
│   │   └── tasks/restore.yml
│   └── validation/
│       ├── defaults/main.yml
│       ├── handlers/main.yml
│       ├── tasks/main.yml
│       ├── tasks/health.yml
│       ├── tasks/schema.yml
│       └── tasks/connectivity.yml
├── group_vars/
│   ├── all.yml
│   ├── local.yml
│   ├── tailscale.yml
│   ├── macos.yml
│   └── secrets.yml
├── host_vars/
│   ├── localhost.yml
│   ├── macbook-pro-m1pro.yml
│   └── tailnet-macbook-pro-m1pro.yml
├── templates/
│   ├── common/
│   │   ├── docker-compose.yml.j2
│   │   ├── env.j2
│   │   ├── healthcheck.sh.j2
│   │   └── backup-manifest.yml.j2
│   ├── registries/
│   │   ├── acp-agent.json.j2
│   │   ├── ans-agent.json.j2
│   │   ├── registry-agent.json.j2
│   │   ├── a2a-agent-card.json.j2
│   │   ├── mcp-server.json.j2
│   │   └── telegram-agent.json.j2
│   ├── macos/
│   │   ├── launchd-plist.j2
│   │   ├── resource-budget.yml.j2
│   │   └── local-services.yml.j2
│   └── security/
│       ├── clawvisor-policy.yml.j2
│       └── acl.yml.j2
├── files/
│   ├── schemas/
│   │   ├── acp-registry.schema.json
│   │   ├── ans.schema.json
│   │   ├── agentregistry.schema.json
│   │   ├── a2a-agent-card.schema.json
│   │   ├── mcp-server.schema.json
│   │   └── telegram-agent.schema.json
│   └── scripts/
│       ├── validate-json.sh
│       └── health-check.sh
└── scripts/
    ├── bootstrap.sh
    ├── backup.sh
    ├── restore.sh
    ├── validate.sh
    └── sync-registries.sh
```

## Master task tree

### 1. Bootstrap the repo
1. Create `ansible/ansible.cfg`.
2. Create `ansible/requirements.yml`.
3. Create `ansible/README.md`.
4. Create base inventories under `inventory/`.
5. Create shared variables under `group_vars/` and `host_vars/`.

### 2. Build identity foundation
1. Create `roles/acp_registry`.
2. Create `roles/ans/`.
3. Create `roles/agentregistry/`.
4. Create `roles/a2a_registry/`.
5. Add schemas in `files/schemas/`.
6. Add shared registry templates in `templates/registries/`.

### 3. Build tool access and security
1. Create `roles/mcpjungle/`.
2. Create `roles/clawvisor/`.
3. Add `templates/security/clawvisor-policy.yml.j2`.
4. Add MCP server templates and onboarding tasks.

### 4. Build communications layer
1. Create `roles/telegram/`.
2. Add polling and webhook tasks.
3. Add bot registration templates.
4. Add group chat onboarding and validation tasks.

### 5. Build runtime layer
1. Create `roles/openclaw/`.
2. Create `roles/hermes/`.
3. Create `roles/macos_clawdev/`.
4. Create `roles/macos_hermesdev/`.
5. Add launchd plist templates.
6. Add resource budget templates.

### 6. Build networking layer
1. Create `roles/tailscale/`.
2. Add Tailscale-aware inventory and host vars.
3. Add localhost and tailnet bind variables.
4. Add connectivity validation tasks.

### 7. Build lifecycle operations
1. Create `roles/backup/`.
2. Create `roles/validation/`.
3. Create top-level playbooks:
   - `bootstrap.yml`
   - `validate.yml`
   - `maintenance.yml`
   - `rollback.yml`
   - `backup.yml`
   - `restore.yml`

### 8. Build top-level stack orchestration
1. Create `playbooks/master-stack.yml`.
2. Create role includes for:
   - ACP
   - ANS
   - Agent Registry
   - A2A
   - MCPJungle
   - Clawvisor
   - Telegram
   - OpenClaw
   - Hermes
   - macOS agent variants
   - Tailscale
3. Ensure the master stack can run phase-by-phase.

### 9. Add Mac-specific deployment
1. Install `roles/macos_clawdev/`.
2. Install `roles/macos_hermesdev/`.
3. Generate launchd plists.
4. Set CPU and RAM caps.
5. Configure localhost + Tailscale access.
6. Validate Apple Silicon compatibility.

### 10. Add sync and validation
1. Create registry sync tasks across ACP, ANS, Agent Registry, and A2A.
2. Add validation for MCPJungle and Clawvisor.
3. Add Telegram health and group chat checks.
4. Add end-to-end connectivity checks.

## Phase order for execution

| Phase | Goal | Key outputs |
|---|---|---|
| Phase 0 | Repo bootstrap | ansible.cfg, inventory, base vars |
| Phase 1 | Identity | ACP, ANS, Agent Registry, A2A |
| Phase 2 | Security/tools | MCPJungle, Clawvisor |
| Phase 3 | Communications | Telegram |
| Phase 4 | Runtime | OpenClaw, Hermes, Docker roles |
| Phase 5 | MacOS | launchd, resource budgets, tailnet |
| Phase 6 | Operations | backup, restore, validation |
| Phase 7 | Orchestration | master-stack.yml, sync tasks |

## Core playbooks to implement

- `playbooks/site.yml`
- `playbooks/master-stack.yml`
- `playbooks/bootstrap.yml`
- `playbooks/validate.yml`
- `playbooks/maintenance.yml`
- `playbooks/rollback.yml`
- `playbooks/backup.yml`
- `playbooks/restore.yml`
- `playbooks/acp-registry.yml`
- `playbooks/ans.yml`
- `playbooks/agentregistry.yml`
- `playbooks/a2a-registry.yml`
- `playbooks/mcpjungle.yml`
- `playbooks/clawvisor.yml`
- `playbooks/telegram.yml`
- `playbooks/openclaw.yml`
- `playbooks/hermes.yml`
- `playbooks/macos-clawdev.yml`
- `playbooks/macos-hermesdev.yml`
- `playbooks/tailscale.yml`

## Minimum acceptance checklist

- ACP registry deploys and validates.
- ANS deploys and resolves agent identity.
- Agent Registry dashboard deploys.
- A2A registry deploys and validates live agent cards.
- MCPJungle deploys and registers approved servers.
- Clawvisor enforces policy boundaries.
- Telegram group communication works.
- Generic OpenClaw and Hermes dockerized agents deploy.
- Noesis ClawDev and Noesis HermesDev deploy on macOS.
- launchd plists are generated and installed.
- Tailscale connectivity works for remote management and agent communication.
- Registries stay synchronized.
- Backup, restore, and rollback workflows exist.
- Master stack orchestration runs phase-by-phase.
