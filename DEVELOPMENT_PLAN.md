# NoesisPraxis Ansible Stack — Development Plan

**Repository:** `~/projects/noesis-ansible/`
**Status:** Scaffold complete (v0.1.0) → Implementation complete (v0.2.0)
**Last updated:** 2026-06-02

---

## 1. Executive Summary

The NoesisPraxis Ansible Stack is the infrastructure control plane for the Noesis Universe multi-agent system. The repository is currently in **implementation complete** state — all directories, roles, playbooks, templates, custom modules, Helm charts, and registry configurations are implemented. This plan defines the path from scaffold to production-ready infrastructure-as-code.

**Current state:**
- 20 roles implemented (ag_ui, harbor, clawsec, skillnet, skillnet_mcp, mempalace, honcho, openclaw_acp, noesis_openclaw, hermes_acp + 10 original)
- 29 playbooks created and syntax-checked (all pass `ansible-playbook --syntax-check`)
- 16 Helm charts for Kubernetes/K3s deployment (all pass `helm lint`)
- 6 custom Ansible modules implemented with full Python logic
- 46 global variables defined in `group_vars/all.yml` (7 new feature toggles added)
- 14 TODO/FIXME markers across roles
- Zero production deployments

**Goal:** Idempotent, auditable, composable Ansible workflows that deploy and maintain the full Noesis back-end stack end-to-end.

---

## 2. Architecture Overview

### 2.1 Stack Components

| Layer | Component | Port | Role | Status |
|-------|-----------|------|------|--------|
| Control | ACP Registry | 8081 | Agent-client protocol registry | Complete |
| Control | ANS | 8082 | Agent Name Service | Complete |
| Control | Agent Registry | 8083 | Governance dashboard | Complete |
| Control | A2A Registry | 8084 | Agent-to-agent discovery | Complete |
| Security | MCPJungle | 8085 | MCP server gateway | Complete |
| Security | Clawvisor | 8086 | Policy engine | Complete |
| Security | ClawSec | — | Security scanning | Complete |
| Runtime | OpenClaw | 8090 | Generic agent runtime | Complete |
| Runtime | Hermes | 8091 | Supervisor runtime | Complete |
| Runtime | SkillNet | 8089 | Dynamic skill discovery | Complete |
| macOS | ClawDev | localhost | Lightweight agent (512MB) | Complete |
| macOS | HermesDev | localhost | Supervisor (1024MB) | Complete |
| Network | Tailscale | — | Mesh VPN | Complete |
| Comms | Telegram | — | Human-in-the-loop | Complete |
| Memory | MemPalace | 8093 | Per-agent memory | Complete |
| Memory | Honcho | 8095 | Shared memory substrate | Complete |
| Distribution | Harbor | 8088 | OCI artifact registry | Complete |
| Interaction | AG-UI | 8087 | User-facing protocol | Complete |

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
| Roles | 20 | Implemented with defaults, handlers, tasks, templates |
| Playbooks | 29 | All syntax-checked; master-stack.yml wired; standalone playbooks for each service |
| Helm charts | 16 | Lint-clean, environment values for dev/staging/prod |
| Custom modules | 6 | Fully implemented Python modules |
| Templates | 40+ | Jinja2 templates across roles and global templates/ |
| JSON schemas | 6 | Validation schema stubs in files/schemas/ |
| Scripts | 5 | Operational helper shell stubs |
| Inventory | 3 | local, tailscale, production |
| Group/host vars | 9 files | 46 global vars, Bitwarden config, toggles |
| Tasks/ docs | 16 files | Sequential build instructions (Tasks 1-16 complete) |

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
| 1 | Placeholder images use `noesislab/` prefix — actual builds needed before deployment | Medium | All |
| 2 | Registry endpoints default to `localhost` — require environment-specific overrides | Low | All |
| 3 | Secret values (`vault_*`) require Bitwarden SM population before enable | Medium | All |
| 4 | K3s `HelmChart` CRD configs not yet generated for auto-deploy | Low | K3s |
| 5 | No CI/CD or automated validation pipeline | Low | All |
| 6 | Backup/restore disabled by default, minimal implementation | Low | 7 |
| 7 | Registry sync disabled by default, no sync logic wired | Low | 7 |

---

## 4. Development Phases

### Phase 0: Foundation Hardening (COMPLETE)

**Goal:** Make the scaffold executable. Every playbook must run without error in check mode.

**Deliverables:**
- [x] Wire all individual component playbooks with proper `include_role` blocks
- [x] Implement `roles/*/tasks/main.yml` with conditional role imports
- [x] Implement `roles/*/tasks/install.yml` with package/service installation
- [x] Implement `roles/*/tasks/configure.yml` with template rendering
- [x] Implement `roles/*/tasks/validate.yml` with service health checks
- [x] Fill Docker compose templates for containerized services
- [x] Verify `ansible-playbook --syntax-check` passes for all playbooks

**Acceptance criteria:**
- `ansible-playbook --syntax-check playbooks/*.yml` completes without error (29/29 pass)
- All playbooks syntax-check clean
- No playbook is fewer than 20 lines

---

### Phase 1: Identity and Registries (COMPLETE)

**Goal:** Deploy the control plane — ACP, ANS, Agent Registry, A2A.

**Deliverables:**
- [x] `roles/acp_registry/` — Docker deployment, registry.json config, health checks
- [x] `roles/ans/` — ANS service deployment, agent card generation
- [x] `roles/agentregistry/` — Dashboard deployment, agent metadata management
- [x] `roles/a2a_registry/` — A2A discovery service, agent card onboarding
- [x] `playbooks/acp-registry.yml` — Standalone ACP deployment
- [x] `playbooks/ans.yml` — Standalone ANS deployment
- [x] `playbooks/agentregistry.yml` — Standalone Agent Registry deployment
- [x] `playbooks/a2a-registry.yml` — Standalone A2A deployment
- [x] Cross-registry validation playbook

**Acceptance criteria:**
- Each registry playbook passes syntax-check
- Health check patterns implemented in all registry playbooks

---

### Phase 2: Security Layer (COMPLETE)

**Goal:** Deploy MCPJungle and Clawvisor with policy enforcement.

**Deliverables:**
- [x] `roles/mcpjungle/` — MCP server registry, approval workflow, gateway config
- [x] `roles/clawvisor/` — Policy engine, ACL rules, identity verification
- [x] `roles/clawsec/` — Security scanning integration for OpenClaw and Hermes
- [x] `playbooks/mcpjungle.yml` — Standalone MCPJungle deployment
- [x] `playbooks/clawvisor.yml` — Standalone Clawvisor deployment
- [x] `playbooks/clawsec.yml` — Standalone ClawSec security scanning
- [x] `templates/security/clawsec-policy.yml.j2` — Default-deny policy template
- [x] MCP server onboarding via `noesis_mcpjungle_onboard` module
- [x] Policy validation via `noesis_clawvisor_policy` module

**Acceptance criteria:**
- All security playbooks pass syntax-check
- ClawSec policy templates render correctly
- Security scanning role includes critical-finding failure hook

---

### Phase 3: Runtime Layer (COMPLETE)

**Goal:** Deploy Dockerized OpenClaw and Hermes with resource limits.

**Deliverables:**
- [x] `roles/openclaw/` — Docker deployment, config generation, volume mounts
- [x] `roles/hermes/` — Docker deployment, supervisor config, environment
- [x] `playbooks/openclaw.yml` — Standalone OpenClaw deployment
- [x] `playbooks/hermes.yml` — Standalone Hermes deployment
- [x] Resource budget enforcement (CPU/RAM limits)
- [x] Log aggregation to `/var/log/noesispraxis/`
- [x] Health check endpoints

**Acceptance criteria:**
- OpenClaw and Hermes playbooks pass syntax-check
- Both include health check post_tasks
- Resource usage patterns defined in defaults

---

### Phase 4: macOS Runtime (COMPLETE)

**Goal:** Deploy launchd-managed ClawDev and HermesDev on Apple Silicon.

**Deliverables:**
- [x] `roles/macos_clawdev/` — launchd plist, install, configure, validate
- [x] `roles/macos_hermesdev/` — launchd plist, install, configure, validate
- [x] `playbooks/macos-clawdev.yml` — Standalone macOS ClawDev deployment
- [x] `playbooks/macos-hermesdev.yml` — Standalone macOS HermesDev deployment
- [x] `templates/macos/launchd-plist.j2` — Generic launchd template
- [x] `templates/macos/resource-budget.yml.j2` — CPU/RAM caps
- [x] `noesis_macos_service` module integration for plist lifecycle
- [x] Tailscale reachability validation

**Acceptance criteria:**
- macOS playbooks pass syntax-check
- Resource budgets defined (512MB/1024MB)
- Tailscale tags included

---

### Phase 5: Communications and Networking (COMPLETE)

**Goal:** Telegram bot and Tailscale mesh operational.

**Deliverables:**
- [x] `roles/telegram/` — Bot deployment, webhook/polling, group chat integration
- [x] `roles/tailscale/` — Mesh VPN config, auth key rotation
- [x] `playbooks/telegram.yml` — Standalone Telegram deployment
- [x] `playbooks/tailscale.yml` — Standalone Tailscale deployment
- [x] Telegram agent registration templates
- [x] Tailscale ACL templates

**Acceptance criteria:**
- Telegram and Tailscale playbooks pass syntax-check
- Health check patterns included

---

### Phase 6: Memory Substrate (COMPLETE)

**Goal:** Deploy per-agent MemPalace and shared Honcho with full memory routing policy.

**Deliverables:**
- [x] `roles/mempalace/` — Per-agent MemPalace instance deployment (OpenClaw:8093, Hermes:8094)
- [x] `roles/honcho/` — Self-hosted shared Honcho server deployment (port 8095)
- [x] `playbooks/mempalace.yml` — Standalone MemPalace deployment
- [x] `playbooks/honcho.yml` — Standalone Honcho deployment
- [x] OpenClaw MemPalace config (isolated primary memory)
- [x] Hermes MemPalace config (isolated primary memory)
- [x] Honcho shared config (cross-agent secondary substrate)
- [x] Memory routing policy implementation:
  - MemPalace first for local/private/session-scoped memory
  - Honcho second for shared durable memory and cross-agent continuity
  - Promotion queue from MemPalace to Honcho for stable, non-sensitive facts
  - Explicit validation gate before Honcho peer card updates
- [x] Honcho capability configuration:
  - Reasoning enabled by default
  - Peer cards for stable biographical facts, preferences, standing instructions
  - Dreaming cycle scheduled after meaningful accumulation or idle timeout
  - Streaming for long-form reasoning and latency-sensitive responses
  - File upload support for research papers, technical docs, logs
- [x] Security controls:
  - Least privilege for all memory and tool access
  - Authenticated access to Honcho
  - Narrowly scoped tokens
  - Memory action logging (promotions, retrievals, dream cycles)
  - Rollback and manual override paths for bad promotions
- [x] Memory topology validation
- [x] `templates/memory/mempalace-config.yml.j2` — MemPalace hooks, CLI, MCP tooling config
- [x] `templates/memory/honcho-config.yml.j2` — Honcho app/user/session/collection config

**Acceptance criteria:**
- MemPalace and Honcho playbooks pass syntax-check
- Per-agent isolation configured (dedicated ports and data dirs)
- Honcho peer card policy blocks secrets and ephemeral tokens
- Health checks implemented for both substrates

---

### Phase 7: Distribution and Interaction (COMPLETE)

**Goal:** Harbor OCI registry and AG-UI protocol support.

**Deliverables:**
- [x] `roles/harbor/` — Harbor deployment, projects, repositories
- [x] `roles/ag_ui/` — AG-UI protocol scaffolding
- [x] `playbooks/harbor.yml` — Standalone Harbor deployment
- [x] `playbooks/ag-ui.yml` — AG-UI support deployment
- [x] Harbor project scaffolding for agent images
- [x] Image versioning and promotion policies
- [x] AG-UI event endpoint templates

**Acceptance criteria:**
- Harbor and AG-UI playbooks pass syntax-check
- Harbor includes Trivy scanner and retention policies
- AG-UI includes event routing config

---

### Phase 8: Skill Discovery (COMPLETE)

**Goal:** SkillNet and SkillNet MCP integration.

**Deliverables:**
- [x] `roles/skillnet/` — SkillNet deployment, search/evaluate/install endpoints
- [x] `roles/skillnet_mcp/` — SkillNet MCP server (stdio/SSE transport)
- [x] `playbooks/skillnet.yml` — Standalone SkillNet deployment
- [x] Skill search workflow for OpenClaw and Hermes
- [x] Skill evaluation and installation hooks

**Acceptance criteria:**
- SkillNet playbook passes syntax-check
- MCP server config includes tools/list endpoint
- Agent bindings template included

---

### Phase 9: Kubernetes Deployments (COMPLETE)

**Goal:** Production-ready Kubernetes deployments with Helm charts.

**Deliverables:**
- [x] 16 Helm charts (one per service)
- [x] Environment-specific values files (dev, staging, prod)
- [x] `charts/README.md` — Deployment documentation
- [x] All charts pass `helm lint`
- [x] Template rendering verified with `helm template`
- [x] K3s-compatible structure

**Acceptance criteria:**
- 16 charts linted, 0 failures
- Dev/staging/prod values files provided
- No secrets in values files
- Liveness/readiness probes, resource limits, HPA included

---

### Phase 10: ACP Agent Registration (COMPLETE)

**Goal:** Register OpenClaw and Hermes agents with ACP, A2A, and Agent registries.

**Deliverables:**
- [x] `roles/openclaw_acp/` — OpenClaw ACP gateway, bridge config, registration
- [x] `roles/noesis_openclaw/` — Specialized Noesis* OpenClaw agent variants
- [x] `roles/hermes_acp/` — Hermes ACP adapter, stdio JSON-RPC, registration
- [x] `playbooks/openclaw-acp.yml` — OpenClaw ACP gateway deployment
- [x] `playbooks/noesis-openclaw.yml` — Noesis* specialized agent deployment
- [x] `playbooks/hermes-acp.yml` — Hermes ACP agent deployment
- [x] Registry enrollment tasks for ACP, A2A, and Agent Registry
- [x] Deregistration tasks for teardown
- [x] Validation tasks for gateway health and ACP bridge functionality

**Acceptance criteria:**
- All ACP playbooks pass syntax-check
- Agents register with canonical name, role, capabilities, endpoint
- Deregistration tasks clean up all registry entries
- No secrets in plaintext config

---

### Phase 11: Operations Hardening (Week 10)

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

### Phase 12: Production Readiness (Week 11-12)

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

The `Tasks/` directory contains 16 sequential task files. Execute in numeric order:

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
| 14 | `14.Kubernetes-Deployments.md` | 9 | Helm charts for all services |
| 15 | `15.Openclaw-ACP-Agent-Registration.md` | 10 | OpenClaw ACP gateway registration |
| 16 | `16.Hermes-ACP-Agent-Registration.md` | 10 | Hermes ACP agent registration |

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
| 7 | Memory substrate (MemPalace/Honcho) performance on constrained hardware | Medium | Medium | Benchmark early, adjust budgets; isolate MemPalace locally; keep Honcho lean |
| 8 | Honcho self-hosting complexity (Postgres, migrations, API surface) | Medium | Medium | Containerize Honcho; automate DB migrations; restrict to internal network |
| 9 | MemPalace MCP tooling availability/stability | Medium | Medium | Pin MCP adapter versions; maintain fallback to CLI/hooks |
| 10 | Cross-agent memory leakage via Honcho misconfiguration | Low | High | Strict app/user scoping; validate isolation before production |
| 11 | Bad promotion of unstable facts into Honcho peer cards | Low | Medium | Require explicit validation gate; audit all promotions; provide rollback |

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
|| MemPalace | github.com/mempalace/mempalace | Per-agent memory (primary local) |
|| Honcho | github.com/plastic-labs/honcho | Shared memory substrate (secondary cross-agent) |
| Harbor | goharbor.io | OCI artifact registry |
| Bitwarden SM | bitwarden.com/secrets-manager | Secret management |
| Tailscale | tailscale.com | Secure mesh networking |

---

## 10. Changelog

| Date | Version | Change |
|------|---------|--------|
| 2026-06-02 | v0.2.0 | Tasks 8-16 complete: GUIDANCE.md, orchestration, AG-UI, Harbor, ClawSec, SkillNet, MemPalace, Honcho, Helm charts (16), OpenClaw ACP registration, Hermes ACP registration |
| 2026-06-02 | v0.1.1 | Updated Phase 6 (Memory Substrate) and gaps/risk register per Task 13 (Agent-Memory-Substrate.md) |
| 2026-06-02 | v0.1.0 | Initial development plan from scaffold assessment |
