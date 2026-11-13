# MCP Gateway & Registry on noesis-lab k3s

Pinned upstream: agentic-community/mcp-gateway-registry
`ec4ad0a4295ee22f59953a7086931b1fe16b9b93` (chart mcp-gateway-registry-stack 0.1.0, images `public.ecr.aws/p3v1o3c6` tag `1.36.0`).

Does not modify MCPJungle.

## Target

- Inventory: `inventory/mcp-gateway-k8s/hosts.ini` group `mcp_gateway_k8s`
- Host alias: `noesis-lab` (OS/tailnet). Kubernetes node: `noesis-praxis`
- kubeconfig: `/etc/rancher/k3s/k3s.yaml` context `default`
- Namespace / release: `mcp-gateway` / `mcp-gateway`
- Storage: `local-path`
- Exposure: Tailscale operator Ingress class `tailscale`, hostname `mcp-gateway`
  (MagicDNS `https://mcp-gateway.tailf99a0.ts.net/`)

## Enablement

Role and inventory keep `mcp_gateway_k8s_enabled` and `mcp_gateway_k8s_expose_enabled` false.

```bash
ansible-playbook -i inventory/mcp-gateway-k8s/hosts.ini playbooks/mcp-gateway-k8s.yml \
  --syntax-check
ansible-playbook -i inventory/mcp-gateway-k8s/hosts.ini playbooks/mcp-gateway-k8s.yml \
  -e mcp_gateway_k8s_enabled=true -e mcp_gateway_k8s_expose_enabled=true -l localhost
```

## Auth and telemetry

- Auth provider: Keycloak bundled by the stack chart (`generateSecrets: true`).
- Chart ingress (ALB) stays disabled; Tailscale Ingress is applied separately.
- `registry.app.mcpTelemetryDisabled: true` and empty OTLP endpoint.

## Backup / rollback

- Backup tag writes Helm history only (no values dump).
- Rollback: `helm rollback mcp-gateway -n mcp-gateway`

## Health

Registry probes use `/health` (upstream deployment template).
