# USER.md — NoesisPraxis Operator Profile

## Identity

**Name:** Elvis Nuno  
**Contact:** elvis.nuno@protonmail.com  
**Location:** Missoula, Montana (America/Denver)  
**Roles:**
- President of Network Engineering & Operations, ServerDomes
- Founder, Ryno Crypto Mining Services
- Infrastructure engineer: DevOps, ISP/WAN, RF, cloud, K8s, blockchain, DePIN, Bitcoin mining

---

## Core Domains

| Tier | Area | Depth |
|------|------|-------|
| Primary | Infrastructure automation (Ansible, Terraform, K8s, Helm) | Expert |
| Primary | ISP/datacenter networking, fiber WAN, edge infrastructure | Expert |
| Primary | Bitcoin mining operations, liquid cooling, energy optimization | Expert |
| Primary | DevOps, CI/CD, observability, SRE practices | Expert |
| Secondary | RF engineering, systems design, ARM/RISC/x86 SBCs | Advanced |
| Secondary | Blockchain, DePIN, Web3 protocol design, treasury management | Advanced |
| Secondary | AI agent infrastructure, multi-agent orchestration, MCP | Advanced |
| Tertiary | Privacy tooling, OPSEC, home automation, security research | Competent |

---

## Operating Style

- **Systems thinker:** Reasons in terms of control planes, failure modes, rollback paths, observability, and blast radius.
- **Security-first:** Defense-in-depth, zero-trust, least privilege by default. Assumes breach.
- **Self-hosted bias:** Prefers open systems, self-hosted infrastructure, and verifiable behavior over convenience SaaS.
- **Production-minded:** Every answer should be deployable, not just discussable. Wants metrics, logs, and guardrails from day one.
- **Direct communication:** Concise, technical, dense. No fluff. Lead with the answer, explain if asked.
- **Structured input/output:** Prefers numbered lists, tables, explicit constraints. Provides exact file paths and URLs.
- **Root-cause fixer:** When given options, consistently chooses Option A — the direct, structural fix over workarounds.

---

## Technology Adoption Criteria

When evaluating new tools or platforms, three questions filter every decision:

1. **Does it reduce operational complexity?** If it adds moving parts without proportional value, reject.
2. **Does it improve security posture?** If it introduces opaque trust or weak auditability, reject.
3. **Does it have a viable economic model?** If it depends on hype or unsustainable subsidies, reject.

Hype and market pressure are not valid selection criteria. Stability over trend, discipline over convenience.

---

## Security & Privacy Posture

- **Zero-trust default:** No implicit trust inside or outside the perimeter. mTLS, mutual auth, certificate pinning.
- **Secret hygiene:** Bitwarden Secrets Manager for all credentials. No hardcoded secrets, no env var leakage, no log exposure.
- **Privacy stack:** ProtonMail, ProtonVPN, TOR, TailsOS, NYM. Minimizes telemetry, avoids opaque dependencies.
- **Operational security:** Sensitive to credential handling, logging scope, third-party data exposure, hidden dependencies.
- **Approval gates:** No live execution on production or financial systems without explicit human authorization.

---

## Agent Design Preferences

When designing or operating AI agents:

| Principle | Implementation |
|-----------|---------------|
| Explicit supervisor/worker separation | No ambiguous hierarchy; clear task delegation boundaries |
| Stateless workers | Side effects must be auditable, reversible, and explicit |
| Structured configs over imperative code | YAML/JSON policies, deterministic guardrails |
| Sandboxing by default | Resource caps, network isolation, filesystem restrictions |
| Least privilege | Agents get minimum viable permissions; escalate with approval |
| Rollback mechanisms | Every change has an undo path; snapshots before mutation |
| Infra-as-code deployments | Ansible, Terraform, Helm — versioned, reviewed, reproducible |
| Observability from day one | Metrics, logs, health checks, not afterthoughts |

---

## Active Projects

| Project | Path | Stack | Status |
|---------|------|-------|--------|
| NoesisPraxis Ansible Stack | `~/projects/noesis-ansible/` | Ansible, Docker, K8s, Helm, Tailscale | Active development |
| TerraHash Autopilot | `~/projects/terrahash-autopilot/` | TypeScript, LangChain, ElizaOS, x402 | Active development |
| Ryno TerraHash Blade | `~/projects/RynoCrypto/ryno-prd/active/ths-blade/` | Hardware PRD, Braiins, supply chain | Active development |
| Braiins Insights MCP | `~/projects/RynoCrypto/braiins-insights-mcp-server/` | TypeScript, MCP, SSE | Active development |
| MISJustice Alliance | `~/projects/MISJustice-Alliance/` | Web, advocacy, research | Active |

---

## Communication Preferences

**Best results come from:**
- Short, direct opening summary — no preamble
- Technical depth only where it changes the design decision
- Compact tables for comparisons and status
- Concrete snippets: YAML, JSON, shell, Python, Go, Rust
- Explicit failure modes, observability hooks, and safe defaults
- Exact file paths and commands, not abstractions

**Avoid:**
- Basic explanations of infrastructure, networking, or DevOps concepts
- Generic AI-agent advice without operational detail
- Hand-wavy recommendations without security/cost/failure analysis
- Architectures dependent on opaque trust, weak auditability, or SaaS lock-in
- Live financial or destructive automation without safeguards and rollback

---

## Memory Architecture

| Layer | System | Purpose | Priority |
|-------|--------|---------|----------|
| Primary local | MemPalace | Per-agent memory, private context | First |
| Secondary shared | Honcho | Cross-agent durable context | Reconcile after MemPalace |
| Wiki | `~/wiki/` | Authoritative documentation source | Always current |

**Rule:** Never overwrite local/private memory with shared context. Reconcile MemPalace first, then Honcho for shared durable state.

---

## Practical Defaults

Assume unless told otherwise:
- Comfortable with Linux, networking, cloud, automation, and low-level systems
- Prefers self-hosted or open-source where feasible
- Willing to trade convenience for control, privacy, and robustness
- Values verifiable behavior over trust-by-documentation
- Wants production-applicable answers, not conceptual discussions
- No live execution on production without explicit approval
- Main wiki is ALWAYS `~/wiki/` — not domain-specific wikis

---

## What to Avoid

- Overly basic explanations of known domains
- Generic advice without implementation detail
- Recommendations without security, cost, or failure-mode analysis
- Opaque trust architectures or unnecessary SaaS dependencies
- Destructive automation without approval gates and rollback paths
- Overwriting local memory with shared context
- Imperative phrasing in persistent memory (save facts, not directives)
