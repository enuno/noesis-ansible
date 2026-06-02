# NoesisPraxis Ansible Stack — Development Plan

**Repository:** `~/projects/noesis-ansible/`
**Status:** Scaffold complete (v0.1.0) → Implementation phase
**Last updated:** 2026-06-02

---

## 1. Executive Summary

The NoesisPraxis Ansible Stack is the infrastructure control plane for the Noesis Universe multi-agent system. The repository is currently in **scaffold phase** — all directories, roles, playbooks, templates, and custom modules are created with baseline structure. This plan defines the path from scaffold to production-ready infrastructure-as-code.

**Current state:**
- 16 roles scaffolded (38-180 lines each)
- 20 playbooks created (master-stack.yml is the only fully wired orchestrator)
- 6 custom Ansible modules implemented with full Python logic
- 39 global variables defined in `group_vars/all.yml`
- 14 TODO/FIXME markers across roles
- Zero production deployments

**Goal:** Idempotent, auditable, composable Ansible workflows that deploy and maintain the full Noesis back-end stack end-to-end.

---

## 2. Architecture Overview

### 2.1 Stack Components

| Layer | Component | Port | Role | Status |
|-------|-----------|------|------|--------|
| Control | ACP Registry | 8081 | Agent-client protocol registry | Scaffold |
| Control | ANS | 8082 | Agent Name Service | Scaffold |
| Control | Agent Registry | 8083 | Governance dashboard | Scaffold |
| Control | A2A Registry | 8084 | Agent-to-agent discovery | Scaffold |
| Security | MCPJungle | 8085 | MCP server gateway | Scaffold |
| Security | Clawvisor | 8086 | Policy engine | Scaffold |
| Security | ClawSec | — | Security scanning | Not started |
| Runtime | OpenClaw | 8090 | Generic agent runtime | Scaffold |
| Runtime | Hermes | 8091 | Supervisor runtime | Scaffold |
| Runtime | SkillNet | — | Dynamic skill discovery | Not started |
| macOS | ClawDev | localhost | Lightweight agent (512MB) | Scaffold |
| macOS | HermesDev | localhost | Supervisor (1024MB) | Scaffold |
| Network | Tailscale | — | Mesh VPN | Scaffold |
| Comms | Telegram | — | Human-in-the-loop | Scaffold |
| Memory | MemPalace | — | Per-agent memory | Not started |
| Memory | Honcho | — | Shared memory substrate | Not started |
| Distribution | Harbor | — | OCI artifact registry | Not started |
| Interaction | AG-UI | — | User-facing protocol | Not started |

### 2.2 Phase Architecture

The `master-stack.yml` orchestrator runs in 8 phases:

```
PHASE 0  Bootstrap        → Host prep, secrets, preflight
PHASE 1  Identity         → ACP, ANS, Agent Registry, A2A
PHASE 2  Security         → MCPJungle, Clawvisor, ClawSec policies
PHASE 3  Runtime          → OpenClaw, Hermes (Docker)
PHASE 4  macOS            → ClawDev, HermesDev (launchd)
PHASE 5  Communications   → Telegram bot
PHASE 6  Networking       → Tailscale mesh
PHASE 7  Sync & Backup    → Registry sync, backup/restore
PHASE 8  Validation       → Health, schema, connectivity
```

---

## 3. Current State Assessment

### 3.1 What Exists

| Area | Count | State |
|------|-------|-------|
| Roles | 16 | Scaffolded with defaults, handlers, task stubs |
| Playbooks | 20 | master-stack.yml wired; others are 6-line stubs |
| Custom modules | 6 | Fully implemented Python modules |
| Templates | 24 | Jinja2 stubs across roles and global templates/ |
| JSON schemas | 6 | Validation schema stubs in files/schemas/ |
| Scripts | 5 | Operational helper shell stubs |
| Inventory | 3 | local, tailscale, production |
| Group/host vars | 9 files | 39 global vars, Bitwarden config, toggles |
| Tasks/ docs | 13 files | Sequential build instructions |

### 3.2 Custom Modules (Complete)

| Module | Lines | Functions | Purpose |
|--------|-------|-----------|---------|
| `noesis_registry_sync.py` | 228 | 3 | Cross-registry sync (ACP ↔ ANS ↔ Agent Registry ↔ A2A) |
| `noesis_mcpjungle_onboard.py` | 253 | 7 | MCP server registration and approval |
| `noesis_vault_rotate.py` | 226 | 3 | Ansible Vault secret rotation |
| `noesis_clawvisor_policy.py` | 223 | 6 | Policy CRUD for Clawvisor |
| `noesis_macos_service.py` | 325 | 13 | launchd plist generation and lifecycle |
| `noesis_bws_secret.py` | 254 | 3 | Bitwarden Secrets Manager integration |

### 3.3 Gaps and Blockers

| # | Gap | Severity | Blocking Phase |
|---|-----|----------|----------------|
| 1 | Individual playbooks (acp-registry.yml, ans.yml, etc.) are 6-line stubs with no role includes | High | All |
| 2 | Role task files contain scaffold logic, not actual service deployment | High | All |
| 3 | Docker compose templates are empty stubs | High | 3 |
| 4 | launchd plist templates are empty stubs | High | 4 |
| 5 | No Harbor role or playbook exists | Medium | Distribution |
| 6 | No AG-UI role or playbook exists | Medium | Interaction |
| 7 | No SkillNet role or playbook exists | Medium | Runtime |
| 8 | No ClawSec integration beyond task 11 doc | Medium | Security |
| 9 | MemPalace and Honcho memory substrate not implemented | Medium | Memory |
| 10 | Registry sync disabled by default, no sync logic wired | Low | 7 |
| 11 | Backup/restore disabled by default, minimal implementation | Low | 7 |
| 12 | No CI/CD or automated validation pipeline | Low | All |

---

## 4. Development Phases

### Phase 0: Foundation Hardening (Week 1)

**Goal:** Make the scaffold executable. Every playbook must run without error in check mode.

**Deliverables:**
- [ ] Wire all 18 individual component playbooks with proper `include_role` blocks
- [ ] Implement `roles/*/tasks/main.yml` with conditional role imports
- [ ] Implement `roles/*/tasks/install.yml` with package/service installation
- [ ] Implement `roles/*/tasks/configure.yml` with template rendering
- [ ] Implement `roles/*/tasks/validate.yml` with service health checks
- [ ] Fill Docker compose templates for containerized services (ACP, ANS, Agent Registry, A2A, MCPJungle, OpenClaw, Hermes)
- [ ] Verify `ansible-playbook --check` passes for all playbooks

**Acceptance criteria:**
- `ansible-playbook --check -i inventory/local/hosts.ini playbooks/site.yml` completes without error
- All 20 playbooks syntax-check clean
- No playbook is fewer than 20 lines

---

### Phase 1: Identity and Registries (Week 2)

**Goal:** Deploy the control plane — ACP, ANS, Agent Registry, A2A.

**Deliverables:**
- [ ] `roles/acp_registry/` — Docker deployment, registry.json config, health checks
- [ ] `roles/ans/` — ANS service deployment, agent card generation
- [ ] `roles/agentregistry/` — Dashboard deployment, agent metadata management
- [ ] `roles/a2a_registry/` — A2A discovery service, agent card onboarding
- [ ] `playbooks/acp-registry.yml` — Standalone ACP deployment
- [ ] `playbooks/ans.yml` — Standalone ANS deployment
- [ ] `playbooks/agentregistry.yml` — Standalone Agent Registry deployment
- [ ] `playbooks/a2a-registry.yml` — Standalone A2A deployment
- [ ] Cross-registry validation playbook

**Acceptance criteria:**
- Each registry responds on its designated port (8081-8084)
- `curl http://localhost:8081/health` returns 200
- Registry sync module can read from all four endpoints
- Agent cards validate against JSON schemas

---

### Phase 2: Security Layer (Week 3)

**Goal:** Deploy MCPJungle and Clawvisor with policy enforcement.

**Deliverables:**
- [ ] `roles/mcpjungle/` — MCP server registry, approval workflow, gateway config
- [ ] `roles/clawvisor/` — Policy engine, ACL rules, identity verification
- [ ] `roles/clawsec/` — Security scanning integration for OpenClaw and Hermes
- [ ] `playbooks/mcpjungle.yml` — Standalone MCPJungle deployment
- [ ] `playbooks/clawvisor.yml` — Standalone Clawvisor deployment
- [ ] `templates/security/clawvisor-policy.yml.j2` — Default-deny policy template
- [ ] MCP server onboarding via `noesis_mcpjungle_onboard` module
- [ ] Policy validation via `noesis_clawvisor_policy` module

**Acceptance criteria:**
- MCPJungle registers and proxies approved MCP servers
- Clawvisor enforces default-deny on unapproved tools
- Security scanning runs on agent skill changes
- Policy changes are auditable and reversible

---

### Phase 3: Runtime Layer (Week 4)

**Goal:** Deploy Dockerized OpenClaw and Hermes with resource limits.

**Deliverables:**
- [ ] `roles/openclaw/` — Docker deployment, config generation, volume mounts
- [ ] `roles/hermes/` — Docker deployment, supervisor config, environment
- [ ] `playbooks/openclaw.yml` — Standalone OpenClaw deployment
- [ ] `playbooks/hermes.yml` — Standalone Hermes deployment
- [ ] Resource budget enforcement (CPU/RAM limits)
- [ ] Log aggregation to `/var/log/noesispraxis/`
- [ ] Health check endpoints

**Acceptance criteria:**
- OpenClaw responds on port 8090
- Hermes responds on port 8091
- Both containers restart on failure
- Resource usage stays within defined limits

---

### Phase 4: macOS Runtime (Week 5)

**Goal:** Deploy launchd-managed ClawDev and HermesDev on Apple Silicon.

**Deliverables:**
- [ ] `roles/macos_clawdev/` — launchd plist, install, configure, validate
- [ ] `roles/macos_hermesdev/` — launchd plist, install, configure, validate
- [ ] `playbooks/macos-clawdev.yml` — Standalone macOS ClawDev deployment
- [ ] `playbooks/macos-hermesdev.yml` — Standalone macOS HermesDev deployment
- [ ] `templates/macos/launchd-plist.j2` — Generic launchd template
- [ ] `templates/macos/resource-budget.yml.j2` — CPU/RAM caps
- [ ] `noesis_macos_service` module integration for plist lifecycle
- [ ] Tailscale reachability validation

**Acceptance criteria:**
- `launchctl list | grep com.noesis` shows loaded services
- ClawDev uses ≤512MB RAM, HermesDev uses ≤1024MB RAM
- Services bind to localhost + tailnet
- Ansible can manage macOS host over Tailscale

---

### Phase 5: Communications and Networking (Week 6)

**Goal:** Telegram bot and Tailscale mesh operational.

**Deliverables:**
- [ ] `roles/telegram/` — Bot deployment, webhook/polling, group chat integration
- [ ] `roles/tailscale/` — Mesh VPN config, auth key rotation
- [ ] `playbooks/telegram.yml` — Standalone Telegram deployment
- [ ] `playbooks/tailscale.yml` — Standalone Tailscale deployment
- [ ] Telegram agent registration templates
- [ ] Tailscale ACL templates

**Acceptance criteria:**
- Telegram bot responds to `/health` in group chat
- Tailscale shows all nodes in tailnet
- macOS host reachable via Tailscale IP from control node

---

### Phase 6: Memory Substrate (Week 7)

**Goal:** Deploy per-agent MemPalace and shared Honcho.

**Deliverables:**
- [ ] `roles/mempalace/` — Per-agent MemPalace instance deployment
- [ ] `roles/honcho/` — Shared Honcho server deployment
- [ ] `playbooks/mempalace.yml` — Standalone MemPalace deployment
- [ ] `playbooks/honcho.yml` — Standalone Honcho deployment
- [ ] OpenClaw MemPalace config (isolated)
- [ ] Hermes MemPalace config (isolated)
- [ ] Honcho shared config (cross-agent)
- [ ] Memory topology validation

**Acceptance criteria:**
- Each agent has isolated MemPalace instance
- Honcho accessible to all agents
- Memory write/read round-trip validates
- No cross-agent memory leakage

---

### Phase 7: Distribution and Interaction (Week 8)

**Goal:** Harbor OCI registry and AG-UI protocol support.

**Deliverables:**
- [ ] `roles/harbor/` — Harbor deployment, projects, repositories
- [ ] `roles/ag_ui/` — AG-UI protocol scaffolding
- [ ] `playbooks/harbor.yml` — Standalone Harbor deployment
- [ ] `playbooks/ag-ui.yml` — AG-UI support deployment
- [ ] Harbor project scaffolding for agent images
- [ ] Image versioning and promotion policies
- [ ] AG-UI event endpoint templates

**Acceptance criteria:**
- Harbor UI accessible, projects created
- Agent images pushable to Harbor
- AG-UI endpoints respond with valid events

---

### Phase 8: Skill Discovery (Week 9)

**Goal:** SkillNet and SkillNet MCP integration.

**Deliverables:**
- [ ] `roles/skillnet/` — SkillNet deployment, search API
- [ ] `roles/skillnet_mcp/` — SkillNet MCP server
- [ ] `playbooks/skillnet.yml` — Standalone SkillNet deployment
- [ ] Skill search workflow for OpenClaw and Hermes
- [ ] Skill evaluation and installation hooks

**Acceptance criteria:**
- Skill search returns results
- Skill installation is idempotent
- MCP tools reflect installed skills

---

### Phase 9: Operations Hardening (Week 10)

**Goal:** Backup, restore, sync, validation, rollback production-ready.

**Deliverables:**
- [ ] `roles/backup/` — Full backup automation
- [ ] `roles/registry_sync/` — Cross-registry sync enabled and wired
- [ ] `roles/validation/` — Comprehensive health, schema, connectivity checks
- [ ] `playbooks/backup.yml` — Scheduled backup execution
- [ ] `playbooks/restore.yml` — Point-in-time restore
- [ ] `playbooks/validate.yml` — Full stack validation
- [ ] `playbooks/rollback.yml` — Controlled rollback
- [ ] `playbooks/maintenance.yml` — Rolling maintenance windows
- [ ] `scripts/sync-registries.sh` — Registry sync helper

**Acceptance criteria:**
- Backup captures all registry state and configs
- Restore validates integrity before applying
- Registry sync is atomic and auditable
- Rollback completes within 5 minutes
- Validation runs in under 2 minutes

---

### Phase 10: Production Readiness (Week 11-12)

**Goal:** Production inventory, monitoring, documentation, CI/CD.

**Deliverables:**
- [ ] `inventory/production/` — Full production inventory
- [ ] Monitoring and alerting integration
- [ ] Log aggregation and rotation
- [ ] Secret rotation automation
- [ ] Performance benchmarking
- [ ] Security audit and penetration testing
- [ ] Complete API documentation
- [ ] Operator runbook
- [ ] CI/CD pipeline (GitHub Actions or similar)

**Acceptance criteria:**
- Production deploy completes without manual intervention
- Monitoring alerts on service degradation
- Security scan passes with zero critical findings
- Documentation covers all operational procedures
- CI/CD runs full validation on every commit

---

## 5. Task Execution Order

The `Tasks/` directory contains 13 sequential task files. Execute in numeric order:

| # | File | Phase | Focus |
|---|------|-------|-------|
| 1 | `1.Task-NoesisPraxis-Ansible-Monorepo.md` | 0 | Complete repo skeleton |
| 2 | `2.Task-NoesisPraxis-Ansible-Scaffolding.md` | 0 | site.yml, master-stack.yml |
| 3 | `3.Task-NoesisPraxis-Ansible-Repo-Scaffolding.md` | 0 | README, ansible.cfg, requirements.yml |
| 4 | `4.Task-NoesisPraxis-Ansible-Inventory-Scaffolding.md` | 0 | local, tailscale, production inventories |
| 5 | `5.Task-NoesisPraxis-Ansible-Role-Scaffolding.md` | 0-1 | All 16 roles with task stubs |
| 6 | `6.Task-NoesisPraxis-Ansible-Template-Scaffolding.md` | 0-1 | Templates, schemas, scripts |
| 7 | `7.Task-NoesisPraxis-Ansible-Final-Task.md` | 0 | Complete scaffold in single pass |
| 8 | `8.Guidance.md` | All | Operating principles and constraints |
| 9 | `9.Orchestration_and_Lifecycle.md` | All | Execution model, phases, idempotency |
| 10 | `10.Support_and_Management_Infrastructure.md` | 7-8 | AG-UI, Agent Registry, Harbor |
| 11 | `11.Agent-Security.md` | 2 | ClawSec integration |
| 12 | `12.Agent-Skills.md` | 8 | SkillNet and SkillNet MCP |
| 13 | `13.Agent-Memory-Substrate.md` | 6 | MemPalace and Honcho |

---

## 6. Design Principles

### 6.1 Idempotency
- Every role must be safely re-runnable
- Handlers trigger only on actual changes
- Check mode (`--check`) must not produce false positives

### 6.2 Secrets Management
- Source of truth: Bitwarden Secrets Manager
- Local cache: Ansible Vault-managed files
- Rotation: `noesis_vault_rotate` module
- Zero hardcoded credentials in templates, playbooks, or defaults

### 6.3 Composability
- Each role is self-contained
- Playbooks include only needed roles
- Tags support partial execution
- `master-stack.yml` orchestrates; individual playbooks deploy

### 6.4 Local-First
- Develop and test on `inventory/local/`
- Tailscale inventory for remote macOS
- Production inventory gated behind explicit approval

### 6.5 macOS Native
- launchd for service management
- User-space paths only
- Conservative resource budgets
- Tailscale for remote access

---

## 7. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|------------|--------|------------|
| 1 | Upstream projects (AG-UI, A2A, etc.) change APIs before implementation | Medium | High | Pin versions in requirements, monitor upstream |
| 2 | macOS launchd behavior differs across macOS versions | Medium | Medium | Test on target version (M1 Pro, macOS latest) |
| 3 | Docker resource limits conflict with macOS Docker Desktop | Low | Medium | Use Docker Desktop resource prefs, validate |
| 4 | Tailscale auth keys expire during automation | Low | High | Implement key rotation, use ephemeral keys |
| 5 | Bitwarden API rate limits during bulk secret fetch | Low | Medium | Cache secrets, implement backoff |
| 6 | Registry sync creates circular dependencies | Medium | High | Implement sync ordering, validate DAG |
| 7 | Memory substrate (MemPalace/Honcho) performance on constrained hardware | Medium | Medium | Benchmark early, adjust budgets |

---

## 8. Metrics and Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| Playbook syntax-check pass rate | 100% | `find playbooks -name '*.yml' -exec ansible-playbook --syntax-check {} \;` |
| Check-mode completion | 100% | `ansible-playbook --check playbooks/site.yml` |
| Role idempotency | 100% | Second run produces 0 changes |
| Deployment time (local) | <10 min | `time ansible-playbook playbooks/site.yml` |
| Rollback time | <5 min | `time ansible-playbook playbooks/rollback.yml` |
| Validation time | <2 min | `time ansible-playbook playbooks/validate.yml` |
| Test coverage (custom modules) | >80% | `pytest tests/` |
| Security scan pass | 0 critical | ClawSec scan |

---

## 9. References

- **Goal:** `Goal-AI-Agent-Infrastructure.md` — Canonical mandate and upstream references
- **Repo Layout:** `Repo-Layout.md` — Master task tree and build order
- **Agent Context:** `AGENTS.md` — Quick reference for agent operations
- **Claude Context:** `CLAUDE.md` — Claude-specific development guidance
- **Wiki:** `~/wiki/noesis-ansible.md` — External documentation

### Upstream Projects

| Project | URL | Role |
|---------|-----|------|
| AG-UI | github.com/ag-ui-protocol/ag-ui | User-facing interaction |
| Agent Registry | github.com/agentregistry-dev/agentregistry | Governance dashboard |
| ANS | github.com/ruvnet/Agent-Name-Service | Secure agent naming |
| ACP | agentclientprotocol.com | Agent-client protocol |
| A2A | github.com/a2aproject/A2A | Agent-to-agent discovery |
| OpenClaw | github.com/openclaw/openclaw | Generic agent runtime |
| MCPJungle | github.com/mcpjungle/MCPJungle | MCP gateway |
| Clawvisor | github.com/clawvisor/clawvisor | Security gatekeeper |
| ClawSec | prompt.security/clawsec | Security scanning |
| SkillNet | github.com/zjunlp/SkillNet | Dynamic skill discovery |
| MemPalace | github.com/mempalace/mempalace | Per-agent memory |
| Honcho | github.com/plastic-labs/honcho | Shared memory substrate |
| Harbor | goharbor.io | OCI artifact registry |
| Bitwarden SM | bitwarden.com/secrets-manager | Secret management |
| Tailscale | tailscale.com | Secure mesh networking |

---

## 10. Changelog

| Date | Version | Change |
|------|---------|--------|
| 2026-06-02 | v0.1.0 | Initial development plan from scaffold assessment |
