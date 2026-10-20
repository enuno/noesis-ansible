# Noesis Praxis single-node k3s operator runbook

This is the unified operator sequence for `noesis-praxis` (`31.97.209.57`,
Ubuntu 26.04 x86_64). The resolved controller workspace is:

```text
/Users/elvis/projects/noesis-ansible
```

All commands below start in that directory unless they explicitly say they run
on the target. No command in this runbook was run against the target while this
runbook was authored. Remote writes require the separate operator approval
before execution.

## 1. Prerequisites and secret inputs

Controller prerequisites:

- Ansible Core 2.18 or newer, Python 3, SSH client, and access to the repository.
- `ansible.posix`, `community.general`, `community.docker`, and
  `kubernetes.core` collections from `requirements.yml`.
- Provider-console SSH access as `elvis` with sudo on `31.97.209.57`.
- A separately stored, Ansible-Vault-encrypted vars file. Never put it in this
  repository or shell history.
- Tailnet administrator approval for the device, MagicDNS, and tailnet HTTPS.
  Tailscale Serve HTTPS requires MagicDNS and tailnet HTTPS to be enabled; a
  new device or tagged device may also require admin/device approval.

Secret injection **names only**:

- `vault_tailscale_auth_key` (passed to the role only as `tailscale_authkey`).
- `hermes_agent_dashboard_username` (optional; defaults to `hermes-admin`).
- `hermes_agent_dashboard_password` (required vault input, minimum 16 characters).
- `hermes_agent_provider_env`, containing **only** the provider API-key env names
  required by the configured model provider; do not put dashboard env keys in it.
- `hermes_agent_dashboard_public_url` (the exact tailnet HTTPS origin) and
  `hermes_agent_dashboard_trusted_proxies` (observed narrow `/32` or `/128`
  proxy sources) are required non-secret deployment inputs when the dashboard is
  enabled. `hermes_agent_bootstrap_overwrite` defaults false; set it true only
  for one approved reseed, then restore false.

No Bitwarden item reference or interactive Tailscale enrollment path is assumed.
The Tailscale play fails closed when a new enrollment is needed and
`vault_tailscale_auth_key` is absent, unless the operator explicitly sets
`tailscale_up_skip=true`. It stats `/var/lib/tailscale/tailscaled.state` without
reading it. If durable state exists while the CLI is absent, installation runs
with `tailscale up` skipped so tailscaled can recover that identity; the final
status check must then show `Running` or the play fails, never auto-enrolls.
A healthy enrolled identity is detected read-only and preserved: the play skips
`tailscale up`, never logs out, and never re-enrolls that identity.

Set only the encrypted file path in the shell:

```bash
cd /Users/elvis/projects/noesis-ansible
export PRAXIS_VAULT_FILE=/absolute/path/to/encrypted-praxis-k3s-vault.yml
```

## 2. Exact execution order

### 2.1 Install controller dependencies

```bash
cd /Users/elvis/projects/noesis-ansible
ansible-galaxy collection install -r requirements.yml
```

### 2.2 Offline syntax and inventory gates

These commands contact no target:

```bash
ansible-playbook --syntax-check -i inventory/praxis-k3s/hosts.ini playbooks/k3s-install.yml
ansible-playbook --syntax-check -i inventory/praxis-k3s/hosts.ini playbooks/k3s-verify.yml
ansible-playbook --syntax-check -i inventory/praxis-k3s/hosts.ini playbooks/tailscale-install.yml
ansible-playbook --syntax-check -i inventory/praxis-k3s/hosts.ini playbooks/hermes-deploy.yml
ansible-playbook --syntax-check -i inventory/praxis-k3s/hosts.ini playbooks/hermes-verify.yml
ansible-playbook --syntax-check -i inventory/praxis-k3s/hosts.ini playbooks/tailscale-serve.yml
ansible-playbook --syntax-check -i inventory/praxis-k3s/hosts.ini playbooks/tailscale-serve-verify.yml
ansible-playbook --list-hosts -i inventory/praxis-k3s/hosts.ini playbooks/tailscale-install.yml
```

The final command must select exactly one host: `noesis-praxis` in
`k3s_server`.

### 2.3 Approved read-only remote preflight

Run only after remote-contact approval. These commands do not modify the host:

```bash
ansible -i inventory/praxis-k3s/hosts.ini k3s_server -m ansible.builtin.ping
ansible -i inventory/praxis-k3s/hosts.ini k3s_server -b -m ansible.builtin.command -a 'uname -m'
ansible -i inventory/praxis-k3s/hosts.ini k3s_server -b -m ansible.builtin.command -a 'apt-cache policy tailscale'
ansible -i inventory/praxis-k3s/hosts.ini k3s_server -b -m ansible.builtin.command -a 'tailscale version'
```

The last command may fail when Tailscale is not installed; record that as
`absent`, not as an invented version. Save the successful `tailscale version`
and `apt-cache policy tailscale` outputs with the live change record. Exact
numeric apt pinning is deferred until this official target repository metadata
is available.

Check mode is planning evidence only. Package/repository simulation does not
prove installation, service state, enrollment, Kubernetes readiness, Helm
atomic behavior, provider connectivity, or Serve routing. The integrated
Tailscale role deliberately performs some read-only status commands even in
check mode, and a host without the binary cannot provide those facts. Do not
use check-mode output as approval to apply:

```bash
ansible-playbook --check --diff -i inventory/praxis-k3s/hosts.ini playbooks/k3s-install.yml --skip-tags bootstrap-python
ansible-playbook --check --diff -i inventory/praxis-k3s/hosts.ini playbooks/tailscale-install.yml -e @"$PRAXIS_VAULT_FILE" --ask-vault-pass
ansible-playbook --check --diff -i inventory/praxis-k3s/hosts.ini playbooks/hermes-deploy.yml -e @"$PRAXIS_VAULT_FILE" --ask-vault-pass
```

### 2.4 Install k3s and verify it

These are remote writes and require approval. The Python bootstrap task is a
separate write gate; keep it skipped when Python 3 is already present.

```bash
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/k3s-install.yml --skip-tags bootstrap-python
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/k3s-verify.yml
```

`k3s-verify.yml` creates and removes a temporary smoke namespace. It proves one
Ready schedulable node, DNS, ClusterIP HTTP, and `local-path` PVC operation.

### 2.5 Install and enroll Tailscale directly on the host

This is a remote write and requires approval:

```bash
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/tailscale-install.yml -e @"$PRAXIS_VAULT_FILE" --ask-vault-pass
```

Safety policy is explicit: `state: present`, stable official apt repository,
Tailscale SSH off, no advertised subnet routes, no exit-node advertising, no
Funnel, and no extra `tailscale up` arguments. `state: present` installs the
repository-current package only when absent and does not auto-upgrade it on an
unchanged rerun. The existing role has no exact-version input, so a numeric
version must not be fabricated. Record the installed version after the live
run:

```bash
ansible -i inventory/praxis-k3s/hosts.ini k3s_server -b -m ansible.builtin.command -a 'tailscale version'
ansible -i inventory/praxis-k3s/hosts.ini k3s_server -b -m ansible.builtin.command -a 'apt-cache policy tailscale'
```

### 2.6 Deploy Hermes

This is a remote write and requires approval:

```bash
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/hermes-deploy.yml -e @"$PRAXIS_VAULT_FILE" --ask-vault-pass
```

The chart is the vendored, pinned chart documented in `pins.md`. The deployment
is one replica with Recreate strategy and a `local-path` PVC. No Ingress,
NodePort, or LoadBalancer is created.

### 2.7 Configure private Tailscale Serve

Before this step, enable MagicDNS and tailnet HTTPS in the Tailscale admin
console and complete any required admin/device approval. Confirm the Hermes
Service is ready, then apply only the HTTPS 443 endpoint:

```bash
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/tailscale-serve.yml -e @"$PRAXIS_VAULT_FILE" --ask-vault-pass
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/tailscale-serve-verify.yml --skip-tags remote-write
```

Follow `docs/praxis-k3s/tailscale-serve.md` to observe the actual backend source
IP, set only the required `/32` trusted proxy, and reseed once if needed. Never
use `0.0.0.0/0` as a trusted proxy. The full Serve verifier's controlled pod
deletion is a separate remote-write approval:

```bash
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/tailscale-serve-verify.yml
```

No host reboot test is part of this runbook or these playbooks.

### 2.8 Final verification and gated tests

Base verification (remote reads plus the documented persistence marker and one
controlled pod recreation) is a remote write and requires approval:

```bash
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/hermes-verify.yml -e @"$PRAXIS_VAULT_FILE" --ask-vault-pass
```

**Chart-test gate:** the chart test uses an isolated `emptyDir`, not the live
PVC, but creates a Kubernetes Job and must be separately authorized. It proves
the CLI, seeded config, and non-strict doctor execution; it does not prove a
provider call:

```bash
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/hermes-verify.yml -e @"$PRAXIS_VAULT_FILE" --ask-vault-pass -e hermes_verify_persistence_test=false -e hermes_chart_test_authorized=true
```

**Provider round-trip gate:** this consumes provider quota and logs the model
exchange. Run only with explicit cost/logging approval:

```bash
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/hermes-verify.yml -e @"$PRAXIS_VAULT_FILE" --ask-vault-pass -e hermes_verify_persistence_test=false -e hermes_provider_test_authorized=true
```

**Independent manual tailnet browser test:** from a different approved device on
the tailnet, not from the server or Ansible controller:

1. Open `https://<device>.<tailnet>.ts.net/` using the MagicDNS name reported by
   Tailscale.
2. Confirm HTTPS has a valid tailnet certificate and the unauthenticated request
   is challenged (HTTP 401), not served publicly.
3. Retrieve dashboard credentials through the approved secret manager outside
   logs/history and authenticate in the browser.
4. Confirm the dashboard loads and a logged-out/private-window request remains
   challenged. Confirm the URL is unreachable from a device outside the
   tailnet. Do not paste credentials into tickets or command output.

### 2.9 Unchanged idempotence rerun and final rechecks

After all approved writes and browser verification, rerun each converged entry
point. An unchanged run must report zero changes; any change is drift and must
be investigated before closure:

```bash
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/k3s-install.yml --skip-tags bootstrap-python
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/tailscale-install.yml -e @"$PRAXIS_VAULT_FILE" --ask-vault-pass
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/hermes-deploy.yml -e @"$PRAXIS_VAULT_FILE" --ask-vault-pass
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/tailscale-serve.yml -e @"$PRAXIS_VAULT_FILE" --ask-vault-pass
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/k3s-verify.yml
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/tailscale-serve-verify.yml --skip-tags remote-write
ansible-playbook -i inventory/praxis-k3s/hosts.ini playbooks/hermes-verify.yml -e @"$PRAXIS_VAULT_FILE" --ask-vault-pass -e hermes_verify_persistence_test=false
```

Final rechecks must include the recorded Tailscale version, active/enabled
`tailscaled` and `k3s`, one Ready Kubernetes node, one Ready Hermes replica,
pinned image digest, Bound PVC, ClusterIP-only exposure, private Serve HTTPS,
HTTP 401 without credentials, Funnel off, and no Tailscale SSH/subnet/exit
advertising.

## 3. Configuration ownership and operational access

Ansible owns:

- Tailscale official apt source/key, installed package state, and service via
  `roles/tailscale`; the tailnet control plane owns the durable device identity.
- `/etc/rancher/k3s/config.yaml`, the k3s systemd unit, and the pinned binary.
- `/etc/rancher/k3s/k3s.yaml`, which stays root-only on the target.
- `/opt/hermes-agent-chart`, `/opt/hermes-agent-stage`, the Helm release,
  Kubernetes objects, and the operator-managed provider Secret.
- The single scoped Tailscale Serve HTTPS 443 endpoint.

Do not edit managed files or Kubernetes objects by hand. Safe operator access is
provider-console SSH to `elvis@31.97.209.57` with sudo for host maintenance and
the tailnet HTTPS URL for the dashboard. Tailscale SSH remains disabled; do not
open subnet routes, exit-node mode, Funnel, public Ingress, NodePort, or
LoadBalancer as a convenience.

`local-path` storage is node-local and non-HA. The Hermes PVC cannot fail over
to another node, and a host/disk loss can lose state without an external
backup. Recreate strategy plus one replica prevents simultaneous writers but
does not create redundancy.

## 4. Upgrades

### Tailscale

1. During an approved preflight, record `tailscale version` and
   `apt-cache policy tailscale` from the official repository.
2. Review release notes and choose an exact supported version. Add and test
   non-invasive exact-version support before changing this runbook; until then,
   keep `state: present`.
3. Back up host state, apply in a maintenance window, record the resulting
   version, and repeat all Tailscale/Serve checks.
4. Never log out or re-enroll a healthy node merely to rotate or upgrade.

### k3s and Hermes

- For k3s, update the exact version and SHA-256 together, back up first, then
  apply and run `k3s-verify.yml`. Follow `k3s.md` for rollback constraints.
- For Hermes, update the vendored chart/version and immutable image digests,
  run chart rendering/schema checks, back up HERMES_HOME, deploy atomically,
  then run base verification, the separately approved chart test, provider
  round-trip, and browser test.

## 5. Backup and recovery

Back up before upgrades or destructive operations. Required backup scope:

- `/var/lib/rancher/k3s/` including server state and node-local PV data.
- The Hermes HERMES_HOME/PVC contents and the exact Helm values/chart pins.
- `/etc/rancher/k3s/` and the Ansible inventory/config needed to recreate the
  host, excluding plaintext credentials.
- Tailnet device/ACL/Serve configuration evidence exported through approved
  administrative channels; enrollment keys are not identity backups.

A crash-consistent host backup should use a provider snapshot or a maintenance
window with k3s stopped. Verify backup checksums and perform a restore drill on
an isolated replacement before relying on it. Recovery order is: provision the
same architecture, restore k3s state and node-local PV data while k3s is
stopped, start k3s, run k3s verification, restore/reconcile Hermes, preserve or
reapprove the Tailscale device identity, reconcile only the scoped Serve
endpoint, then run all final checks. Never restore over a running cluster or
assume `local-path` data exists elsewhere.

## 6. Credential rotation

- Tailscale enrollment key: issue a replacement, update
  `vault_tailscale_auth_key` for future new devices, verify future enrollment,
  revoke the old key, and verify the old key fails. Do not run `tailscale
  logout` or `tailscale up` on this healthy device as part of rotation.
- Provider key: issue new, update `hermes_agent_provider_env`, deploy, run the
  separately approved provider round-trip, revoke old, then verify the old key
  fails without printing either value.
- Dashboard credentials: issue new, update `hermes_agent_dashboard_username`
  and vault-backed `hermes_agent_dashboard_password`, deploy, verify new login,
  revoke/remove old, and verify old
  login fails plus unauthenticated access remains HTTP 401.

## 7. Failure evidence (read-only)

Run on the target through approved SSH. Review and redact hostnames, tailnet
names, IPs, user data, and tokens before sharing; none of these commands should
print an auth key:

```bash
sudo systemctl status tailscaled --no-pager
sudo journalctl -u tailscaled --since '-30 minutes' --no-pager
sudo tailscale status --json
sudo tailscale debug prefs
sudo tailscale serve status --json
sudo tailscale version
apt-cache policy tailscale
sudo systemctl status k3s --no-pager
sudo journalctl -u k3s --since '-30 minutes' --no-pager
sudo k3s kubectl get nodes -o wide
sudo k3s kubectl get pods -A -o wide
sudo k3s kubectl -n hermes-agent describe deployment hermes-agent
sudo k3s kubectl -n hermes-agent get events --sort-by=.lastTimestamp
sudo k3s kubectl -n hermes-agent logs deployment/hermes-agent --tail=200
sudo ss -H -ltnp
```

Do not add `--authkey` to diagnostic commands and do not attach the encrypted
vault file, Kubernetes Secret output, environment dumps, or shell history.

## 8. Disable only this Serve endpoint

This changes only HTTPS port 443 for this device and leaves every other Serve
endpoint, Tailscale identity, Hermes object, PVC, and Secret untouched:

```bash
sudo tailscale serve --https=443 off
```

Do **not** run `tailscale serve reset`.

## 9. DESTRUCTIVE UNINSTALL — NOT EXECUTED

Nothing in this section was executed or authorized. Uninstall can destroy the
only cluster/PVC copy and can remove the tailnet identity. Require a verified
external backup, maintenance window, explicit object-by-object approval, and a
restore test first.

- Disable only this Serve endpoint with the scoped command in section 8; never
  blanket-reset Serve.
- `helm uninstall hermes-agent --namespace hermes-agent` can delete the
  chart-created PVC in this chart. Preserve/verify HERMES_HOME first and do not
  run it as a routine rollback.
- Removing k3s or `/var/lib/rancher/k3s` destroys cluster and node-local PV
  state. Never use an upstream uninstall script or delete those paths without a
  verified restore artifact.
- Running the Tailscale role with `state: absent` invokes logout and removes the
  package, changing the durable tailnet identity. It is forbidden during
  installation, upgrades, key rotation, recovery, or ordinary rollback.
