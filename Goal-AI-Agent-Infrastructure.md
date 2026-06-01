# Goal: AI Agent Infrastructure

## Noesis Universe infrastructure mandate

NoesisPraxis is the Hermes supervisor agent for the Noesis Universe infrastructure stack. Use Ansible as the primary tool for creating, composing, deploying, maintaining, updating, validating, backing up, and rolling back all back-end infrastructure that supports Noesis agents and the services they consume. The repository at `~/projects/noesis-ansible/` is the source of truth for this infrastructure, including agent runtimes, registries, MCP servers, security policy, communications layers, memory substrates, and lifecycle operations.

Hermes must treat the following upstream projects and documentation as canonical references when designing playbooks, roles, inventories, templates, and custom modules:

- AG-UI: https://github.com/ag-ui-protocol/ag-ui and https://docs.ag-ui.com/introduction
- Agent Registry: https://github.com/agentregistry-dev/agentregistry and https://aregistry.ai/docs/quickstart/
- ARegistry quickstart: https://aregistry.ai/docs/quickstart/
- ANS for secure agent naming and discovery: https://github.com/ruvnet/Agent-Name-Service and https://genai.owasp.org/resource/agent-name-service-ans-for-secure-al-agent-discovery-v1-0/
- ACP registry and discovery source material: https://agentclientprotocol.com/rfds/acp-agent-registry and https://github.com/agentclientprotocol/registry
- A2A protocol and discovery guidance: https://github.com/a2aproject/A2A, https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md, and https://github.com/prassanna-ravishankar/a2a-registry
- OpenClaw runtime behavior, tools, and deployment patterns: https://github.com/openclaw/openclaw, https://github.com/openclaw/openclaw/blob/main/docs/cli/agents.md, https://github.com/openclaw/openclaw/blob/main/docs/tools/index.md, https://github.com/openclaw/openclaw/blob/main/docs/gateway/secrets.md, and https://github.com/openclaw/openclaw-ansible
- MCPJungle as the MCP gateway and tool aggregation layer: https://github.com/mcpjungle/MCPJungle and https://docs.mcpjungle.com/
- Clawvisor as the agent gatekeeper and approval layer: https://github.com/clawvisor/clawvisor and https://clawvisor.com/
- Clawsec security scanning for OpenClaw and Hermes: https://prompt.security/clawsec and https://github.com/prompt-security/clawsec/wiki
- SkillNet for dynamic skill search, creation, evaluation, and integration: https://github.com/zjunlp/SkillNet and https://github.com/CycleChain/skillnet-mcp
- Mempalace as the primary per-agent memory substrate: https://github.com/mempalace/mempalace and https://mempalaceofficial.com/guide/mcp-integration.html, https://mempalaceofficial.com/guide/openclaw.html, https://mempalaceofficial.com/guide/hooks.html
- Honcho as the shared secondary memory substrate: https://github.com/plastic-labs/honcho and https://honcho.dev/docs/v3/documentation/introduction/overview, https://honcho.dev/docs/v3/documentation/features/storing-data, https://honcho.dev/docs/v3/documentation/features/get-context, https://honcho.dev/docs/v3/documentation/reference/sdk, https://honcho.dev/docs/v3/documentation/reference/cli
- Harbor as the OCI artifact registry and project administration layer: https://goharbor.io/, https://github.com/goharbor/harbor, https://goharbor.io/docs/2.14.0/install-config/, https://goharbor.io/docs/2.14.0/administration/, and https://goharbor.io/docs/2.14.0/working-with-projects/
- Bitwarden Secrets Manager and the `bws` CLI for secret sourcing: https://bitwarden.com/help/secrets-manager-cli/, https://bitwarden.com/help/secrets-manager-quick-start/, and https://bitwarden.com/products/secrets-manager/
- Tailscale for secure remote management and private agent connectivity: https://tailscale.com/docs and https://tailscale.com/docs/how-to/quickstart

Operating principles:
- Use Ansible as the composable infrastructure control plane for Noesis back-end services, agent deployments, maintenance tasks, updates, backups, and registry synchronization.
- Treat `~/projects/noesis-ansible/` as the source of truth: every deployable service, registry object, policy, memory substrate, or runtime artifact must be represented as code there.
- Keep the repo local-first, idempotent, and phase-driven.
- Use inventories, `group_vars`, and `host_vars` to separate local, Tailscale, and production contexts.
- Use roles for reusable deployment logic, templates for generated config and registry objects, and custom modules only when a reusable Noesis-specific operation is best expressed as code.
- Use tags and phase boundaries so each subsystem can run independently or as part of the full stack.
- Use Ansible Vault for runtime consumption of secrets after they are fetched locally from Bitwarden Secrets Manager using `bws`, so routine Ansible runs do not need to query Bitwarden live.
- Keep secrets out of templates, inventories, and default vars.
- Use Harbor for OCI image distribution and project management when the stack includes containerized artifacts or agent runtimes.
- Use AG-UI for user-facing agent interaction surfaces and Agent Registry / ACP / ANS / A2A for discovery, governance, and identity.
- Use MCPJungle as the MCP gateway and tool-routing layer, Clawvisor as the approval and gatekeeping layer, and Clawsec for security scanning and policy enforcement.
- Use SkillNet and SkillNet MCP for dynamic skill discovery and integration.
- Use Mempalace as the primary per-agent memory substrate and Honcho as the shared secondary memory substrate.
- Use Tailscale for secure remote management and private-agent communication, especially for the MacBook Pro M1 Pro host and any other tailnet-managed machines.
- Use Harbor administration and project controls as the model for lifecycle management of OCI-backed assets, including authentication, project quotas, replication, scanning, auditability, and upgrade planning.

Execution model:
- Prefer declarative tasks over shell commands.
- If a shell command is necessary, keep it short, safe, and idempotent.
- Validate each phase before moving to the next.
- Make rollback, backup, and maintenance paths explicit.
- Maintain launchd-based services for macOS agents and conservative CPU/RAM budgets for the Apple Silicon host.
- Ensure the macOS agents are reachable both locally and over Tailscale when intended.
- Keep MCP servers and directly consumed services managed as first-class infrastructure, not ad hoc runtime dependencies.

Task execution rules:
- Read this Goal file first.
- Then process the files in `./Tasks` sequentially in numeric order by filename, starting at `1` and continuing through `10` and beyond if additional task files exist.
- Do not skip, reorder, or parallelize task files.
- Complete each task fully before moving to the next.
- For each task file:
  - Read it completely.
  - Implement only the work required by that task.
  - Validate the result before continuing.
- If a task depends on a missing file or artifact, create the smallest safe scaffold needed to unblock it, then continue.
- If blocked, stop at the smallest safe boundary and report the exact task file and blocker.

Required outcomes:
- NoesisPraxis must be able to use this repo to deploy and maintain the Noesis Universe infrastructure.
- The repo must manage identity, discovery, registry, agent runtime, communications, Harbor artifacts, security policy, networking, secrets, backup, restore, validation, and rollback as composable Ansible workflows.
- Every change should be auditable, repeatable, and represented in code.
