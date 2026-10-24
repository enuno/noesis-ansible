# NoesisPraxis k3s — Component Documentation

Single-node k3s server. Installed and managed entirely by Ansible; no
install-script side effects, no manual cluster state.

## Host identity vs Kubernetes node identity

These are **deliberately different** and must not be unified:

| | Value | Owned by |
|---|---|---|
| Machine / OS hostname | `noesis-lab` (`noesis-lab.hashgrid.net`, `31.97.209.57`, Ubuntu 26.04.1 LTS) | `hostnamectl` / cloud-init |
| Host tailnet device | `noesis-lab.tailf99a0.ts.net` → `100.119.84.26` | host `tailscaled` |
| **Kubernetes node name** | **`noesis-praxis`** | `k3s_node_name` (pinned) |

The machine was renamed to `noesis-lab` so it stops colliding with the
`noesis-praxis` k3s instance. The Kubernetes node keeps the name
`noesis-praxis` because every local-path PersistentVolume in the cluster
(Buzz Postgres, Buzz git, Hermes data) was provisioned with

```yaml
nodeAffinity:
  required:
    nodeSelectorTerms:
      - matchExpressions:
          - key: kubernetes.io/hostname
            operator: In
            values: [noesis-praxis]
```

and that affinity cannot practically be rewritten on a bound PV. The node
must therefore keep answering to `noesis-praxis`, which is why
`k3s_node_name` is pinned explicitly rather than inherited from the hostname.

**Do not** "fix" the mismatch by aligning the two names, and do not change
`k3s_node_name` on this cluster.

Also note: `noesis-praxis.tailf99a0.ts.net` is **not this host** — it is the
operator-managed Tailscale proxy pod serving the Hermes dashboard Ingress
(`100.86.40.93`). The k3s API does not listen there. Anything needing the
host over the tailnet must use `noesis-lab.tailf99a0.ts.net`.

### Incident this prevents (2026-10-24)

The host was renamed while `k3s_node_name` was unset, so k3s derived the node
name from the OS hostname. On the next reboot kubelet registered a **second,
brand-new node** `noesis-lab.hashgrid.net`; the original `noesis-praxis` node
went `NotReady` and was tainted `node.kubernetes.io/unreachable`. Result:

- every PV-backed workload (`buzz`, `buzz-postgres`, `buzz-redis`,
  `hermes-agent`) stuck `Pending` with
  `didn't match PersistentVolume's node affinity`;
- `mcpjungle` scheduled onto the new node but `CrashLoopBackOff`, because its
  Postgres dependency was one of the unschedulable pods;
- `tailscale-operator` *appeared* healthy throughout — it is stateless, so
  operator health proved nothing about cluster health.

Recovery: pin `node-name`, restart k3s, confirm the original node returns
`Ready` and untainted, then delete the phantom node object. Full sequence in
`RUNBOOK.md` §10.

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
