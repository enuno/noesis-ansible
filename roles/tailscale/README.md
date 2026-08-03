# Tailscale Role

Integrated from [artis3n/ansible-role-tailscale](https://github.com/artis3n/ansible-role-tailscale) into the NoesisPraxis Ansible stack.

## Purpose

Install, configure, and manage Tailscale nodes across Debian, Ubuntu, CentOS/RHEL/Rocky/AlmaLinux, Fedora, Amazon Linux, Arch Linux, and openSUSE.

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `state` | `latest` | `latest`, `present`, or `absent` |
| `tailscale_authkey` | `"{{ vault_tailscale_auth_key | default('') }}"` | Node auth key; defaults to Bitwarden-fetched value |
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

By default the role reads `tailscale_authkey` from `vault_tailscale_auth_key`, which is populated by the `bitwarden_secrets` role from the Bitwarden secret named `TAILSCALE_AUTH_KEY`.

```yaml
- hosts: all
  roles:
    - role: bitwarden_secrets
    - role: tailscale
      vars:
        tailscale_tags:
          - server
          - noesispraxis
```

To override with an explicit key:

```yaml
- hosts: all
  roles:
    - role: tailscale
      vars:
        tailscale_authkey: "tskey-auth-..."
        tailscale_tags:
          - server
          - noesispraxis
```

## Playbook

```bash
# Fetch the ephemeral key from Bitwarden and join the tailnet
export BWS_ACCESS_TOKEN=<your-bws-token>
ansible-playbook -i inventory/local/hosts.ini playbooks/tailscale.yml
```

## Security

- Auth keys are redacted in logs by default (`no_log`)
- State file hashes arguments for idempotency without exposing keys
- OAuth keys require tags; ephemeral/preauthorized flags are configurable
