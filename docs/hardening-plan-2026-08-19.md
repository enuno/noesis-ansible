# Host Network Hardening Plan — 2026-08-19

**Risk tier:** R3 (firewall/DNS changes)
**Status:** EXECUTED 2026-08-19 (operator approval received; see §8)
**Owner:** Noesis Praxis (Hermes supervisor)
**Executor:** noesis-ansible playbook (isolated worker / host-side enforcement)
**Policy reference:** `shared/POLICY.global.md`, `shared/GUARDRAILS.global.yaml`, `platform/risk-tiers.yaml` (in noesis-agent-stack)

---

## 1. Problem statement (verified live 2026-08-19)

- `nftables.service` is **failed**; `netfilter-persistent.service` is **active** (iptables is the effective mechanism).
- IPv4/IPv6 `INPUT` policy is **ACCEPT**.
- Public-interface listeners (0.0.0.0 / *):
  - `22` SSH (management — keep, but restrict)
  - `2022` secondary SSH/ET
  - `3000` dokploy
  - `3210` jot-app
  - `8642` hermes (gateway)
  - `8765` braiins-insights-mcp
  - `7946` Docker Swarm node comm (TCP+UDP)
  - `4097` muxd-hub
- Tailscale is up (`100.106.20.102 noesis-praxis`) and must remain open per operator preference (hardening happens after this pass via Tailscale ACLs + local firewall).

## 2. Target end state

Default-deny inbound on public interfaces; Tailscale (`tailscale0`) fully open; loopback open; established/related allowed; SSH restricted to tailnet + optional management sources; ICMP/ICMPv6 allowed for diagnostics; Docker `FORWARD` left intact to avoid breaking container networking.

Exact ruleset (iptables / netfilter-persistent):

```bash
# IPv4
iptables -P INPUT DROP
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -i tailscale0 -j ACCEPT
iptables -A INPUT -p tcp --dport 22 -j ACCEPT          # management (optionally -s <tailnet/mgmt-cidr>)
iptables -A INPUT -p tcp --dport 2022 -j ACCEPT        # secondary SSH (optionally restricted)
iptables -A INPUT -p icmp -j ACCEPT                    # diagnostics
# Explicitly drop remaining public service ports (defense in depth)
iptables -A INPUT -p tcp --dport 2377 -j DROP          # swarm mgmt
iptables -A INPUT -p tcp --dport 7946 -j DROP          # swarm node TCP
iptables -A INPUT -p udp --dport 7946 -j DROP          # swarm node UDP
iptables -A INPUT -p udp --dport 4789 -j DROP          # VXLAN
# Tailscale UDP transport (public interface) if tailnet needs it inbound
iptables -A INPUT -p udp --dport 41641 -j ACCEPT

# IPv6 (same posture)
ip6tables -P INPUT DROP
ip6tables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
ip6tables -A INPUT -i lo -j ACCEPT
ip6tables -A INPUT -i tailscale0 -j ACCEPT
ip6tables -A INPUT -p ipv6-icmp -j ACCEPT
ip6tables -A INPUT -p tcp --dport 22 -j ACCEPT
ip6tables -A INPUT -p tcp --dport 2022 -j ACCEPT
ip6tables -A INPUT -p tcp --dport 2377 -j DROP
ip6tables -A INPUT -p tcp --dport 7946 -j DROP
ip6tables -A INPUT -p udp --dport 7946 -j DROP
ip6tables -A INPUT -p udp --dport 4789 -j DROP

# Persist
netfilter-persistent save
```

**Service rebinding (separate follow-up):** services that should be tailnet-only
(dokploy :3000, jot-app :3210, hermes :8642, braiins :8765) get rebound to
`100.106.20.102` or `tailscale0` in a later pass; firewall DROP rules above are
the immediate exposure reduction.

## 3. Preflight checks (must pass before apply)

1. Active SSH session on a non-firewall path (or console access) verified.
2. Tailscale reachable (`tailscale status` OK; DNS health warning noted).
3. `netfilter-persistent` is the active mechanism (confirmed).
4. Ruleset syntax validated (`iptables-restore --test < ruleset`).
5. Backup of current ruleset: `iptables-save > /root/fw-backup-2026-08-19.rules`.

## 4. Expected effect

- Public inbound to 3000/3210/8642/8765/7946/4097 blocked at host.
- SSH/2022 remain reachable (restricted later via ACLs per operator preference).
- Tailscale connectivity unchanged.
- Docker container-to-container forwarding unchanged (FORWARD untouched).

## 5. Rollback plan

```bash
# Restore from backup
iptables-restore < /root/fw-backup-2026-08-19.rules
ip6tables-restore < /root/fw-backup6-2026-08-19.rules
netfilter-persistent save
```

Rollback trigger: current session loss, tailnet unreachable, unexpected service
breakage detected within 15 minutes of apply.

## 6. Approval manifest reference

This plan is the action manifest. Execution requires:
- Independent review (scope/safety/rollback) — reviewer route distinct from planner.
- Human operator approval of the exact ruleset above.
- Single-use short-lived execution grant bound to this manifest (per
  `platform/approval-manifest.schema.json`).

**Any change to targets, ports, digests, or rollback invalidates this plan.**

## 7. Open items for operator

- Confirm SSH/2022 source restrictions for this pass (allow all, or tailnet/mgmt CIDR only).
- Confirm whether `4097` (muxd-hub) and `22/2022` should be dropped now or after ACL pass.
- Authorize service rebinding (3000/3210/8642/8765) as part of this pass or a follow-up.

## 8. Execution record (2026-08-19)

**Approval:** Operator (elvis) via CLI — "execute the firewall ruleset from the manifest". Single-use grant bound to this exact manifest; no rule outside the manifest was added.

**Preflight (passed):**
- Passwordless sudo available; session path loopback (127.0.0.1 → 127.0.1.1:22) protected by `-i lo` + established/related.
- Tailscale up (100.106.20.102); netfilter-persistent active; Docker healthy (22 containers).
- Syntax tested via `iptables-restore --test` and `ip6tables-restore --test` — both OK.
- Backups: `/root/fw-backup-2026-08-19.rules` (389 lines), `/root/fw-backup6-2026-08-19.rules` (64 lines); copies in `/home/elvis/`.

**Applied (exact manifest §2 ruleset):**
- IPv4: `-P INPUT DROP`; established/related ACCEPT; lo ACCEPT; tailscale0 ACCEPT; tcp 22/2022 ACCEPT; icmp ACCEPT; tcp 2377/7946 DROP; udp 7946/4789 DROP; udp 41641 ACCEPT.
- IPv6: `-P INPUT DROP`; established/related ACCEPT; lo ACCEPT; tailscale0 ACCEPT; ipv6-icmp ACCEPT; tcp 22/2022 ACCEPT; tcp 2377/7946 DROP; udp 7946/4789 DROP.
- Persisted via `netfilter-persistent save` (exit 0); `/etc/iptables/rules.v4` (23 INPUT refs), `/etc/iptables/rules.v6` (19 refs).

**Verification (all passed):**
- `iptables -S INPUT` / `ip6tables -S INPUT` show `-P INPUT DROP` + full ruleset.
- Current session survived; Tailscale status OK; Docker containers still running; loopback service check (dokploy :3000) returns HTTP 200.

**Result:** Host-local public listeners now default-deny. Hermes :8642, muxd-hub :4097, swarm :7946 and any other host-local public port are blocked except allowed management (22/2022) and Tailscale.

**Residual exposure (documented follow-up, NOT part of this manifest):**
Docker-published ports traverse FORWARD/DOCKER chains, not INPUT: braiins-insights-mcp `0.0.0.0:8765`, jot-app `0.0.0.0:3210`, dokploy `0.0.0.0:3000` remain reachable on the public interface. Closing them requires either:
  a. Service rebinding to tailscale0/127.0.0.1 (manifest §2 follow-up), or
  b. DOCKER-USER DROP rules (e.g. `iptables -I DOCKER-USER -p tcp --dport 8765 -j DROP`).
Either is a NEW R3 change requiring a new approval; it is not implied by this manifest.

**Rollback:** armed. Restore `/root/fw-backup-2026-08-19.rules` + `fw-backup6` via `iptables-restore` / `ip6tables-restore`, then `netfilter-persistent save`. Rollback triggers: session loss, tailnet unreachable, or unexpected service breakage within 15 min of apply.
