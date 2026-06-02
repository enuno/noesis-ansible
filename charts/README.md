# NoesisPraxis Helm Charts

Production-ready Helm charts for the NoesisPraxis agent infrastructure stack.

## Chart Inventory

| Chart | Service Port | Description |
|-------|-------------|-------------|
| openclaw | 8080 | ACP agent orchestrator |
| hermes | 8080 | Hermes agent supervisor |
| acp-registry | 8081 | ACP registry service |
| ans | 8082 | Agent namespace service |
| agentregistry | 8083 | Agent registry |
| a2a-registry | 8084 | A2A registry |
| mcpjungle | 8085 | MCP jungle |
| clawvisor | 8086 | Clawvisor monitoring |
| ag-ui | 8087 | AG-UI protocol layer |
| harbor | 8088 | Harbor OCI registry |
| skillnet | 8089 | SkillNet discovery |
| telegram | 8090 | Telegram gateway |
| tailscale | 8091 | Tailscale mesh |
| mempalace | 8093 | Per-agent memory |
| honcho | 8095 | Shared memory substrate |
| clawsec | 8080 | Security scanning |

## Quick Start

```bash
# Lint a chart
helm lint charts/openclaw

# Template (dry-run)
helm template openclaw charts/openclaw

# Install with environment overrides
helm install openclaw charts/openclaw -f charts/values-dev.yaml
helm install openclaw charts/openclaw -f charts/values-staging.yaml
helm install openclaw charts/openclaw -f charts/values-prod.yaml
```

## K3s Deployment

```bash
# K3s auto-deploys HelmCharts from /var/lib/rancher/k3s/server/manifests/
# Copy rendered manifests or use HelmChart CRD
kubectl apply -f k3s-helmchart-configs/
```

## Validation

All charts pass `helm lint`. Template rendering verified. No secrets in values.
