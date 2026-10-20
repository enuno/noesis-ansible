# Vendored: tailscale-operator 1.104.1

Official Tailscale Kubernetes Operator Helm chart, vendored for air-gapped,
pin-verified installs. Source repo: https://github.com/tailscale/tailscale
(path `cmd/k8s-operator/deploy/chart`), published at
https://pkgs.tailscale.com/helmcharts.

- Chart version: 1.104.1 (appVersion v1.104.1 — matches the previously
  host-installed tailscaled 1.104.1)
- Upstream tgz: tailscale-operator-1.104.1-1791927002-750a04179b2bdd34c73158b501fecfdcda5faec4341c96521c62a0d770f5b8eb.tgz
- Upstream digest (index.yaml): sha256:750a04179b2bdd34c73158b501fecfdcda5faec4341c96521c62a0d770f5b8eb
- Verified digest of the downloaded tgz before extraction.
- Deployment auth: OAuth client credentials ONLY (values `oauth.clientId` /
  `oauth.clientSecret`, secret keys `client_id` / `client_secret`).
  There is NO authKey deployment path in this chart.

Update procedure: bump the version, re-download from pkgs.tailscale.com,
verify the index digest, diff templates, re-run helm lint + the praxis
offline render harness.
