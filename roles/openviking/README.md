# openviking

Ansible role to install, configure, and validate the OpenViking service.

## Requirements

- Target host running systemd
- Network access to GitHub releases (or custom mirror via `openviking_download_url`)

## Role Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `openviking_port` | `8080` | HTTP API and health endpoint port |
| `openviking_install_path` | `/opt/openviking` | Base installation directory |
| `openviking_version` | `latest` | Release version to install |
| `openviking_worker_count` | `0` | Worker processes (0 = auto) |
| `openviking_log_level` | `info` | Logging verbosity |
| `openviking_cluster_mode` | `standalone` | `standalone` or `cluster` |
| `openviking_cluster_join` | `""` | Comma-separated `host:port` list for cluster join |
| `openviking_user` | `openviking` | Service user name |
| `openviking_group` | `openviking` | Service group name |
| `openviking_manage_service` | `true` | Whether to manage the systemd unit |
| `openviking_health_path` | `/health` | Health check HTTP path |
| `openviking_health_timeout` | `10` | Health check timeout in seconds |

## Dependencies

No external Ansible role dependencies. Runtime dependencies (if any) should be documented here once OpenViking upstream specifies them (e.g., Redis, kernel modules).

## Example Playbook

```yaml
- hosts: backend_services
  roles:
    - role: openviking
      vars:
        openviking_port: 9090
        openviking_worker_count: 4
        openviking_log_level: debug
```

## License

MIT
