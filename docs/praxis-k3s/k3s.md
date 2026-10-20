# NoesisPraxis k3s — Component Documentation

Single-node k3s server on `noesis-praxis.hashgrid.net` (31.97.209.57,
Ubuntu 26.04.1 LTS). Installed and managed entirely by Ansible; no
install-script side effects, no manual cluster state.

## Entry Points

```bash
# Install (become: sudo at play level)
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/k3s-install.yml

# Verify (idempotence-safe; smoke namespace is created and always deleted)
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/k3s-verify.yml

# Offline checks
ansible-playbook --syntax-check -i inventory/praxis-k3s/hosts.ini playbooks/k3s-install.yml
ansible-playbook --syntax-check -i inventory/praxis-k3s/hosts.ini playbooks/k3s-verify.yml
```

## Pinned Version

- **k3s:** `v1.37.1+k3s1` (latest stable per
  `https://api.github.com/repos/k3s-io/k3s/releases`, published 2026-09-30;
  first non-prerelease, non-draft release at authoring time).
- **Binary sha256 (amd64 asset `k3s`):**
  `92b94582eb7b34a8cf532e6006842b9ed215a6783cf56a3dd6271fd35243b2c0`,
  taken from the release's `sha256sum-amd64.txt`.
- **Pin locations:** `inventory/praxis-k3s/group_vars/k3s_server.yml`
  (authoritative for this host) and `roles/k3s/defaults/main.yml`
  (role fallback). Keep them in sync.
- **Rationale:** k3s is the cluster control plane. Exact pins make every
  run reproducible and force upgrades to be a deliberate, documented act
  instead of a drifting surprise. The binary is downloaded directly from
  the GitHub release asset and verified with `get_url`'s sha256
  checksum — never piped through an install script.

## Component Matrix

Configured declaratively in `roles/k3s/templates/config.yaml.j2`:

| Component | State | Reason |
|-----------|-------|--------|
| traefik | **disabled** | Ingress is deferred to the application layer; nothing on this host may expose public HTTP(S) listeners. |
| servicelb (klipper-lb) | **disabled** | No LoadBalancer need on a single node; services are ClusterIP-only by policy. |
| coredns | enabled | Cluster DNS (smoke-tested). |
| local-path-provisioner | enabled | Dynamic hostPath PVCs (smoke-tested). |
| metrics-server | enabled | `kubectl top` / HPA baseline. |

## Config Ownership

- `/etc/rancher/k3s/config.yaml` — Ansible-managed (template), root:root `0600`.
- `/etc/systemd/system/k3s.service` — Ansible-managed (template, modeled on
  upstream but declarative).
- `/etc/rancher/k3s/k3s.yaml` — kubeconfig, root:root `0600`; enforced
  explicitly by the role even though k3s defaults match.
- `write-kubeconfig-mode: "0600"` is also set inside the k3s config so the
  server itself re-writes it with correct permissions.

## Idempotence Behavior

- **Re-run with no changes:** install split detects the pinned binary and
  skips the download; configure split changes nothing; no handler fires;
  validate split re-checks health. Zero drift.
- **Config change:** the template notifies the `Restart k3s` handler, which
  restarts **only if the service was already active** (guard fact set in the
  configure split). First-time installs start the service explicitly and
  never trigger a restart.
- **Installed version ≠ pinned version:** hard failure with a clear message.
  This role never upgrades, downgrades, or wipes an existing cluster.

## Upgrade / Rollback (runbook material)

1. Pick the new stable tag from the k3s GitHub releases API and record its
   `sha256sum-amd64.txt` entry for the `k3s` asset.
2. Update both pin locations (group_vars + role defaults) together.
3. Snapshot anything stateful (local-path PV data lives under
   `/var/lib/rancher/k3s/storage/`).
4. Drain is a no-op on a single node; instead: stop workloads, stop the
   service (`systemctl stop k3s`), replace the binary, start, verify with
   `playbooks/k3s-verify.yml`.
5. **Rollback:** the previous pinned binary can be re-downloaded from the
   matching release URL; k3s data in `/var/lib/rancher/k3s/` is
   version-tolerant within a minor series, but restoring from the step-3
   snapshot is the supported path if etcd/state diverges.

## Verification Playbook Notes

`playbooks/k3s-verify.yml` is deliberately separate from install so smoke
tests never contaminate install idempotence. It uses only the `command`
module against `k3s kubectl` (no k8s Python client is guaranteed on the
target), bounds every wait (`--timeout` flags plus Ansible retries), sets
`changed_when: false` on all reads, and creates exactly one temporary
namespace `praxis-smoke-<epoch>` which the `always` cleanup block deletes
and confirms gone before the play can succeed.
