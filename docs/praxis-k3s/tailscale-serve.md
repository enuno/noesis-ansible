# Private Hermes dashboard with Tailscale Serve

This track exposes the separate minimal Hermes dashboard to authenticated
tailnet clients only. It does not alter the node/CNI topology and does not use
Funnel, public Ingress, LoadBalancer, NodePort, `hostPort`, a Kubernetes
Tailscale operator/sidecar, subnet routing, exit-node mode, or Tailscale SSH.

```text
 authorized tailnet client
          |
          | HTTPS + MagicDNS (tailnet only)
          v
 https://<device>.<tailnet>.ts.net:443
          |
          | host-level tailscale serve (Funnel OFF)
          v
 http://<ClusterIP>:9119
          |
          | kube-proxy / flannel service routing
          v
 hermes-agent namespace
 Service/hermes-agent (ClusterIP :9119)
          |
          v
 Hermes pod dashboard (0.0.0.0:9119 in-container, basic auth required)
```

## Prerequisites

1. `roles/tailscale` has installed and enrolled the host using the vault-backed
   `tailscale_authkey`. `tailscale status --json` must say `BackendState` is
   `Running`. The Serve role never logs out or re-enrolls an identity.
2. MagicDNS and HTTPS certificates are enabled for the tailnet. The node must
   have a `<device>.<tailnet>.ts.net` DNS name. Tailscale provisions and renews
   the HTTPS certificate; do not install a public reverse proxy here.
3. The parallel Hermes track has deployed `Service/hermes-agent` in namespace
   `hermes-agent` as ClusterIP on port 9119.
4. Dashboard basic-auth credentials are supplied by the external Secret
   `hermes-agent-provider` through the chart's `extraEnvFrom` path.

## Exact chart values wiring (vendored chart 1.21.0)

These are the actual keys in `charts/vendor/hermes-agent/values.yaml`. This is
an additive group-vars example; merge it into the parallel chart track rather
than creating a second release from this role.

```yaml
# Example inventory/praxis-k3s/group_vars value structure consumed by the
# hermes-agent Helm role. Adapt only the outer variable name to that role.
hermes_agent_values:
  dashboard:
    enabled: true
    auth:
      # Tailscale Serve is not an identity-aware authentication proxy. Use
      # Hermes' own supported basic authentication; credentials remain in the
      # namespace Secret and enter the pod through secretKeyRef entries.
      provider: basic
    publicUrl: "https://{{ tailscale_serve_device_name }}.{{ tailscale_serve_tailnet_name }}.ts.net"
    trustedProxies: "{{ tailscale_serve_dashboard_trusted_proxies }}"
    readinessProbe:
      enabled: true
  service:
    enabled: true
    type: ClusterIP
    port: 9119
  ingress:
    enabled: false
  httpRoute:
    enabled: false
  extraEnvFrom:
    - secretRef:
        name: hermes-agent-provider

# Exposure-track inputs. Defaults are deliberately narrow.
tailscale_serve_device_name: noesis-praxis
tailscale_serve_tailnet_name: example-tailnet
tailscale_serve_dashboard_trusted_proxies:
  - 127.0.0.1/32
  - 100.64.0.0/10
# Mandatory after observing the real source (example only):
# tailscale_serve_confirmed_backend_source_ip: 10.42.0.1
# tailscale_serve_dashboard_trusted_proxies:
#   - 127.0.0.1/32
#   - 100.64.0.0/10
#   - 10.42.0.1/32
```

`dashboard.publicUrl` and `dashboard.trustedProxies` seed
`config.dashboard.public_url` and `config.dashboard.trusted_proxies` in
`HERMES_HOME` (`/opt/data`). If either changes after first deployment, perform
the parallel chart upgrade with `bootstrap.overwrite=true`. Do not leave that
overwrite setting enabled beyond the intended reseed.

Basic auth uses these Secret environment names:
`HERMES_DASHBOARD_BASIC_AUTH_USERNAME` and either
`HERMES_DASHBOARD_BASIC_AUTH_PASSWORD` or
`HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH`.

## Why ClusterIP is the backend

The role reads the Service on the target with:

```bash
sudo k3s kubectl -n hermes-agent get service hermes-agent -o json --request-timeout=15s
```

This path is chosen over `k8s_info` because k3s already bundles a matching
kubectl and kubeconfig at `/etc/rancher/k3s/k3s.yaml`; `k8s_info` would add a
Python Kubernetes-client dependency to the target. On this single-node k3s
host, kube-proxy/flannel makes ClusterIPs reachable from the host. The role
proves TCP reachability before declaring validation complete.

A `127.0.0.1` bridge would require another host process, lifecycle unit, local
listener, and failure/restart policy. Direct ClusterIP routing has fewer moving
parts. Its tradeoff is that the proxy connection can reach the pod with the
host/CNI source address rather than loopback, so trusted-proxy configuration
must be verified against runtime evidence.

## Verify the trusted proxy source

The defaults are `[127.0.0.1/32, 100.64.0.0/10]`; they are not a claim about
the source the pod will actually observe. Deployment validation intentionally
fails until this is confirmed.

1. Run `ip -json route get <ClusterIP>` on the host and record the `prefsrc` as
   a candidate. The role prints this candidate.
2. Send a uniquely timed request through the tailnet URL, then inspect Hermes
   pod request logs (or a temporary, operator-approved request-header logging
   instrument) and identify the immediate proxy peer/source address. Do not
   infer it solely from the route command.
3. Set `tailscale_serve_confirmed_backend_source_ip` to that observed address.
4. If it is outside the defaults, append only `<observed-address>/32` to
   `dashboard.trustedProxies` / `tailscale_serve_dashboard_trusted_proxies`.
5. If config was already seeded, upgrade once with `bootstrap.overwrite=true`,
   then rerun `playbooks/tailscale-serve.yml` and the verification playbook.
6. Confirm an unauthenticated tailnet HTTPS request returns HTTP 401 and that
   forwarded scheme/client handling is correct after authenticated login.

Never use `0.0.0.0/0`: Hermes rejects that unbounded proxy range upstream.

## Reconciliation and verification

```bash
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/tailscale-serve.yml
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/tailscale-serve-verify.yml --skip-tags remote-write
# After explicit approval for one controlled pod restart:
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/tailscale-serve-verify.yml
```

The role parses `tailscale serve status --json`. It changes only when
`https:443` does not point at `http://<ClusterIP>:9119`; a converged run is a
no-op. It never blanket-resets Serve, restarts `tailscaled`, or changes another
endpoint. Every operational wait is bounded. Verification checks enrollment,
assigned IPv4/IPv6/MagicDNS, Funnel-off state, TCP backend reachability, HTTP
401 without credentials, public listeners, and Kubernetes exposure kinds.

The controlled restart task deletes the selected Hermes pod and verifies
Deployment recovery, endpoint convergence, and auth enforcement. It is tagged
`remote-write` so it can be skipped until approved. **No host reboot test is
performed by this track.**

## Disable only this endpoint

Run this on the k3s host:

```bash
sudo tailscale serve --https=443 off
```

The original `--https=443` flag scopes removal to this endpoint. Do **not** run
`tailscale serve reset`: that would remove unrelated Serve configuration.
Disabling Serve does not change the Hermes release, PVC, Secret, dashboard
state, or Tailscale enrollment.

## Credential rotation

- **Dashboard password:** rotate the value in the operator-managed
  `hermes-agent-provider` Secret (password or password hash), roll the Hermes
  Deployment through the parallel Helm track, and verify old credentials fail,
  new credentials work, and an unauthenticated request remains HTTP 401. Never
  place the password in group vars, command output, or this role.
- **Tailscale enrollment key:** auth keys are enrollment credentials, not the
  long-lived device identity. Rotate/revoke keys in the Tailscale admin console
  and update the vault variable `tailscale_authkey` for future enrollment.
  Never log out or re-run `tailscale up` merely to rotate an auth key on an
  already enrolled host; doing so risks replacing the existing identity.

## Offline authoring validation record

Controller-local only; no SSH or cluster contact was made. A non-empty dummy
vault-password file was created outside this repository at
`/Users/elvis/projects/noesis-agent-stack/workspace/orchestrator/scratch/ansible-vault-pass`.

```text
$ ansible-playbook --syntax-check -i inventory/praxis-k3s/hosts.ini playbooks/tailscale-serve.yml

playbook: playbooks/tailscale-serve.yml
$ ansible-playbook --list-hosts -i inventory/praxis-k3s/hosts.ini playbooks/tailscale-serve.yml

playbook: playbooks/tailscale-serve.yml

  play #1 (k3s_server): Configure private Tailscale Serve for Hermes dashboard  TAGS: [tailscale-serve,tailscale]
    pattern: ['k3s_server']
    hosts (1):
      noesis-praxis
$ ansible-playbook --syntax-check -i inventory/praxis-k3s/hosts.ini playbooks/tailscale-serve-verify.yml

playbook: playbooks/tailscale-serve-verify.yml
$ ansible-playbook --list-hosts -i inventory/praxis-k3s/hosts.ini playbooks/tailscale-serve-verify.yml

playbook: playbooks/tailscale-serve-verify.yml

  play #1 (k3s_server): Verify private Tailscale Serve dashboard exposure  TAGS: [tailscale,tailscale-serve,verify]
    pattern: ['k3s_server']
    hosts (1):
      noesis-praxis
```

Both syntax checks passed, and both inventory expansions selected exactly one
host (`noesis-praxis`). A local YAML parse of all six YAML files and
`git diff --check` also passed. Runtime behavior remains intentionally
unverified until an approved target-side run.
