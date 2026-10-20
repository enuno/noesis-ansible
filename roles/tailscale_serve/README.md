# tailscale_serve

Publishes the existing `hermes-agent/hermes-agent` ClusterIP dashboard through
private Tailscale Serve HTTPS. It owns only the `https:443` Serve endpoint. It
does not install/enroll Tailscale, restart `tailscaled`, reset Serve, enable
Funnel, or mutate Kubernetes networking.

## Prerequisites

Run `roles/tailscale` first with vault-backed `tailscale_authkey`. The node must
report `BackendState: Running`, have MagicDNS, and support Tailscale HTTPS.
The separate Hermes release must already expose a ClusterIP Service on 9119.

The role intentionally uses target-side `sudo k3s kubectl`: k3s ships its own
kubectl and kubeconfig, while `k8s_info` would add a target Python Kubernetes
client dependency. All reads have bounded request/command timeouts.

## Variables

See `defaults/main.yml`. At deployment, confirm the backend source address from
Hermes request logs/headers, set `tailscale_serve_confirmed_backend_source_ip`,
and include its narrow `/32` in `tailscale_serve_dashboard_trusted_proxies`.

```yaml
tailscale_serve_actions: [configure, validate]
tailscale_serve_confirmed_backend_source_ip: 10.42.0.1
tailscale_serve_dashboard_trusted_proxies:
  - 127.0.0.1/32
  - 100.64.0.0/10
  - 10.42.0.1/32
```
