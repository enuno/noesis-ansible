# claude_code_bridge Role

Deploys the **Claude Code ↔ Noesis Praxis** development-delegation bridge so
Noesis Praxis (Hermes) can dispatch bounded development tasks to on-demand
Claude Code sessions ("Mother" role) and collect structured results.

Contract lives in `noesis-agent-stack` (`agents/claude-code-worker/`,
`contracts/bridge/`). This role implements the deployment; it does not redefine
policy.

## What it deploys

| Piece | Location (default) | Purpose |
|-------|--------------------|---------|
| Bridge dirs | `~/.hermes/claude-bridge/{inbox,outbox,active,archive}` + `channel.jsonl`, `.last_read`, `.mother_last_read` | File-bridge state shared by Hermes and Claude Code |
| Claude Code hook | `~/.claude/hooks/noesis-bridge-check.py` | Polls bridge on `UserPromptSubmit` (inject context) + `Stop` (post summary) |
| Hook registration | `~/.claude/settings.json` | Adds `UserPromptSubmit` + `Stop` entries (idempotent merge, preserves existing hooks) |
| Skills | `~/.claude/skills/noesis-loop/`, `~/.claude/skills/noesis-status/` | Task cycle + status check for Claude Code sessions |
| Plugin manifest | `~/.local/state/noesis/claude-plugin/.claude-plugin/plugin.json` | Provenance / marketplace-style registration |
| Hermes plugin sync | `~/.hermes/plugins/evey-bridge/` | `claude_bridge_task` / `claude_bridge_message` / `claude_bridge_check` tools |

## Usage

```bash
# Enable (stack toggle)
# group_vars/all.yml: noesispraxis_enable_claude_code_bridge: true

ansible-playbook -i inventory/local/hosts.ini playbooks/claude-code-bridge.yml

# Or as part of the master stack
ansible-playbook -i inventory/local/hosts.ini playbooks/master-stack.yml --tags claude-code-bridge
```

## Delegation flow

1. Noesis Praxis calls `claude_bridge_task` → `inbox/{task_id}.yaml`
   (schema: `contracts/bridge/task.schema.json`).
2. A Claude Code session's `UserPromptSubmit` hook injects the task.
3. The worker executes within task scope, writes
   `outbox/{task_id}.result.yaml` (schema: `contracts/bridge/result.schema.json`).
4. Noesis Praxis calls `claude_bridge_check` → collects results (moves to `active/`).

## Defaults (key)

- `claude_code_bridge_dir`: `~/.hermes/claude-bridge` (matches the Hermes
  `evey-bridge` plugin default `$HERMES_HOME/claude-bridge`)
- `claude_code_bridge_enabled`: mirrors `noesispraxis_enable_claude_code_bridge`
- `claude_code_bridge_channel_max_lines`: 200 (channel compression threshold)
- `claude_code_bridge_archive_retention_days`: 7
- `claude_code_bridge_hook_timeout_s`: 10
- `claude_code_bridge_install_skills`: true
- `claude_code_bridge_sync_hermes_plugin`: true

## Security notes

- Bridge dirs are created `0700`; channel/cursors `0600`.
- No credentials or tokens cross the bridge. Task-scoped grants stay in Hermes.
- Claude Code sessions are ephemeral workers: bounded task, structured result,
  no standing authority (see `noesis-agent-stack` `shared/POLICY.global.md` §1).
- Watch item: the external `42-evey-hermes-plugins-sync.sh` script can
  overwrite the synced Hermes plugin; re-run this role to restore the Noesis
  flavor (files are checksum-synced).

## Verification

The role's `validate.yml` checks: bridge dirs exist, hook installed +
executable + syntactically valid, settings.json has the hook registered (≥2
occurrences), skills present, Hermes plugin present.
