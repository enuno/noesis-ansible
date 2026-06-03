# Tailscale Role

Integrated from [artis3n/ansible-role-tailscale](https://github.com/artis3n/ansible-role-tailscale) into the NoesisPraxis Ansible stack.

## Purpose

Install, configure, and manage Tailscale nodes across Debian, Ubuntu, CentOS/RHEL/Rocky/AlmaLinux, Fedora, Amazon Linux, Arch Linux, and openSUSE.

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `state` | `latest` | `latest`, `present`, or `absent` |
| `tailscale_authkey` | `""` | Node auth key (from vault) |
| `tailscale_args` | `""` | Extra `tailscale up` arguments |
| `tailscale_tags` | `[]` | Tags to apply (without `tag:` prefix) |
| `tailscale_up_timeout` | `"120"` | `tailscale up` timeout in seconds |
| `tailscale_oauth_ephemeral` | `true` | Ephemeral node for OAuth keys |
| `tailscale_oauth_preauthorized` | `false` | Skip manual approval for OAuth |
| `verbose` | `false` | Debug output |
| `tailscale_up_skip` | `false` | Skip `tailscale up` (e.g. AMI build) |
| `release_stability` | `stable` | `stable` or `unstable` |
| `insecurely_log_authkey` | `false` | Log authkey on error (security risk) |
| `auth_key_in_state` | `true` | Include authkey in state hash |

## Usage

```yaml
- hosts: all
  roles:
    - role: tailscale
      vars:
        tailscale_authkey: "{{ vault_tailscale_authkey }}"
        tailscale_tags:
          - server
          - noesispraxis
```

## Playbook

```bash
ansible-playbook -i inventory/local/hosts.ini playbooks/tailscale.yml
```

## Security

- Auth keys are redacted in logs by default (`no_log`)
- State file hashes arguments for idempotency without exposing keys
- OAuth keys require tags; ephemeral/preauthorized flags are configurable
