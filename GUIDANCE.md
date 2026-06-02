# NoesisPraxis Ansible Stack — Operating Guidance

**Repository:** `~/projects/noesis-ansible/`  
**Authority:** NoesisPraxis (Hermes supervisor agent for Noesis Universe)  
**Last updated:** 2026-06-02

---

## 1. Primary Orchestration Mandate

Ansible is the sole infrastructure control plane for all Noesis back-end services, agent deployments, maintenance, updates, backups, registry synchronization, and lifecycle operations. Every deployable service, registry object, policy, memory substrate, or runtime artifact must be represented as code in this repository.

---

## 2. Secrets Management Policy

### 2.1 Source of Truth
- **Bitwarden Secrets Manager** is the canonical secret store.
- Secrets are fetched locally using the `bws` CLI.
- After fetch, secrets are imported into **Ansible Vault**-managed local files.
- Routine Ansible execution consumes Vault-managed local copies — no live Bitwarden queries during normal runs.

### 2.2 Prohibited Practices
- Never hardcode secrets in templates, inventories, playbooks, or role defaults.
- Never commit unencrypted secret values to git.
- Never pass secrets as plain extra vars (`-e`) in production.

### 2.3 Required Practices
- Use `noesis_bws_secret` custom module for Bitwarden fetch operations.
- Use `noesis_vault_rotate` custom module for secret rotation.
- Store vault password in `.vault_pass` (chmod 600, gitignored).
- Set `vault_password_file` in `ansible.cfg`.
- Rotate secrets every 90 days (`secret_max_age_days: 90`).

---

## 3. Idempotency and Composability

### 3.1 Idempotency Rules
- Every role must be safely re-runnable.
- Handlers trigger only on actual changes.
- Check mode (`--check`) must not produce false positives.
- Use `changed_when` and `failed_when` to normalize shell command behavior.

### 3.2 Composability Rules
- Each role is self-contained.
- Playbooks include only needed roles.
- Tags support partial execution.
- `master-stack.yml` orchestrates; individual playbooks deploy single subsystems.
- Use `import_playbook` at top level, `include_role` within plays.

---

## 4. Inventory and Environment Separation

| Environment | Purpose | Inventory Path |
|-------------|---------|----------------|
| local | Development and testing | `inventory/local/hosts.ini` |
| tailscale | Remote management via mesh VPN | `inventory/tailscale/hosts.ini` |
| production | Production deployments | `inventory/production/hosts.ini` |

- Use `group_vars` and `host_vars` for environment-specific defaults.
- Keep production inventory minimal and gated behind explicit approval.
- The macOS host (`macbook-pro-m1pro`) is managed via Tailscale inventory.

---

## 5. Role Structure Convention

Every role must contain:
- `defaults/main.yml` — safe defaults, no secrets
- `handlers/main.yml` — restart/reload triggers
- `tasks/main.yml` — conditional role imports
- `tasks/install.yml` — package/service installation
- `tasks/configure.yml` — template rendering and config
- `tasks/validate.yml` — health checks and verification
- `templates/` — Jinja2 configs, service definitions, policy files

Optional but recommended:
- `tasks/backup.yml` and `tasks/restore.yml`
- `tasks/rollback.yml`
- `meta/main.yml` for dependencies

---

## 6. Template and Schema Policy

- Shared templates live in `templates/` (common/, registries/, macos/, security/).
- JSON schemas live in `files/schemas/` for validation.
- All templates must be valid for their target file type.
- Use placeholders where implementation details are not yet known.
- Keep secrets externalized — templates reference vault variables, never literal values.

---

## 7. macOS and Tailscale Requirements

- macOS deployment target: MacBook Pro M1 Pro, 16 GB RAM.
- Use `launchd` for per-user service management.
- Bind services to localhost and Tailscale as intended, not public interfaces.
- Keep CPU/RAM usage conservative (ClawDev ≤512MB, HermesDev ≤1024MB).
- Ansible reaches macOS host over Tailscale.
- Validate both localhost and tailnet reachability.

---

## 8. MCP and Service Dependency Rules

- MCP servers and agent-consumed services must be defined as code.
- Access to MCP servers is mediated by approved registry entries and policy layers.
- Every service dependency must have install, configure, validate, backup, and restore paths.
- Registry synchronization must be atomic and auditable.

---

## 9. Execution Style

- Prefer declarative tasks over shell commands.
- If a shell command is required, keep it short, safe, and idempotent.
- Use comments only where they clarify operational behavior.
- Avoid Linux-only assumptions in macOS playbooks.
- Avoid assumptions about network topology unless explicitly in inventory or vars.
- Keep the repo safe to run in a local lab before productionizing.

---

## 10. Validation and Rollback

- Validate each phase before moving to the next.
- Make rollback, backup, and maintenance paths explicit.
- Use `playbooks/validate.yml` for full-stack health checks.
- Use `playbooks/rollback.yml` for controlled rollback.
- Use `playbooks/backup.yml` and `playbooks/restore.yml` for data protection.

---

## 11. Task File Execution Order

Process task files in `Tasks/` sequentially by filename:

| # | File | Focus |
|---|------|-------|
| 1 | `1.Task-NoesisPraxis-Ansible-Monorepo.md` | Repo skeleton |
| 2 | `2.Task-NoesisPraxis-Ansible-Scaffolding.md` | Entry playbooks |
| 3 | `3.Task-NoesisPraxis-Ansible-Repo-Scaffolding.md` | README, cfg, requirements |
| 4 | `4.Task-NoesisPraxis-Ansible-Inventory-Scaffolding.md` | Inventories |
| 5 | `5.Task-NoesisPraxis-Ansible-Role-Scaffolding.md` | Role stubs |
| 6 | `6.Task-NoesisPraxis-Ansible-Template-Scaffolding.md` | Templates, schemas, scripts |
| 7 | `7.Task-NoesisPraxis-Ansible-Final-Task.md` | Complete scaffold |
| 8 | `8.Guidance.md` | Operating principles (this file) |
| 9 | `9.Orchestration_and_Lifecycle.md` | Execution model |
| 10 | `10.Support_and_Management_Infrastructure.md` | AG-UI, Harbor, Agent Registry |
| 11 | `11.Agent-Security.md` | ClawSec integration |
| 12 | `12.Agent-Skills.md` | SkillNet MCP |
| 13 | `13.Agent-Memory-Substrate.md` | MemPalace + Honcho |
| 14 | `14.Kubernetes-Deployments.md` | Helm/K3s packaging |
| 15 | `15.Openclaw-ACP-Agent-Registration.md` | OpenClaw ACP gateway |
| 16 | `16.Hermes-ACP-Agent-Registration.md` | Hermes ACP adapter |

---

## 12. Upstream Canonical References

When designing playbooks, roles, templates, or custom modules, consult these sources first:

| Project | Reference URL |
|---------|---------------|
| AG-UI | https://github.com/ag-ui-protocol/ag-ui |
| Agent Registry | https://github.com/agentregistry-dev/agentregistry |
| ANS | https://github.com/ruvnet/Agent-Name-Service |
| ACP | https://agentclientprotocol.com/rfds/acp-agent-registry |
| A2A | https://github.com/a2aproject/A2A |
| OpenClaw | https://github.com/openclaw/openclaw |
| MCPJungle | https://github.com/mcpjungle/MCPJungle |
| Clawvisor | https://github.com/clawvisor/clawvisor |
| ClawSec | https://prompt.security/clawsec |
| SkillNet | https://github.com/zjunlp/SkillNet |
| MemPalace | https://github.com/mempalace/mempalace |
| Honcho | https://github.com/plastic-labs/honcho |
| Harbor | https://goharbor.io/ |
| Bitwarden SM | https://bitwarden.com/products/secrets-manager/ |
| Tailscale | https://tailscale.com/docs |

---

## 13. Compliance Checklist

Before marking any task complete, verify:

- [ ] All new files are under `~/projects/noesis-ansible/`
- [ ] No secrets in plaintext
- [ ] All YAML/JSON syntax valid
- [ ] All playbooks pass `ansible-playbook --syntax-check`
- [ ] All roles are idempotent (second run produces 0 changes)
- [ ] Templates are valid for their target file type
- [ ] Handlers trigger only on change
- [ ] Check mode produces no false positives
- [ ] Documentation updated (README, GUIDANCE, DEVELOPMENT_PLAN)
- [ ] Git commit with descriptive message
