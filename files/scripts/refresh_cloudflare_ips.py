#!/usr/bin/env python3
"""Refresh the vendored Cloudflare origin allow-list in roles/n8n_public_edge.

The firewall rules and nginx's `set_real_ip_from` trust list are both derived
from these ranges, so they are vendored into the role: the repo stays
reproducible and every change to who can reach the origin is a reviewable diff
rather than whatever the API happened to return on the day.

Cloudflare changes these rarely. Run this, read the diff, commit it.

    python3 files/scripts/refresh_cloudflare_ips.py            # show the diff
    python3 files/scripts/refresh_cloudflare_ips.py --write     # apply it

Needs no credentials: https://api.cloudflare.com/client/v4/ips is public.
"""
import argparse
import json
import pathlib
import sys
import urllib.request

API = "https://api.cloudflare.com/client/v4/ips"
DEFAULTS = (pathlib.Path(__file__).resolve().parents[2]
            / "roles" / "n8n_public_edge" / "defaults" / "main.yml")


def fetch():
    with urllib.request.urlopen(API, timeout=30) as fh:
        payload = json.load(fh)
    if not payload.get("success"):
        raise SystemExit("Cloudflare API returned success=false: %s" % payload.get("errors"))
    r = payload["result"]
    v4, v6 = r.get("ipv4_cidrs") or [], r.get("ipv6_cidrs") or []
    if not v4 or not v6:
        # An empty list would render a firewall that admits nobody and a
        # real_ip trust list that trusts nobody. Refuse rather than write it.
        raise SystemExit("refusing to write an empty range list (v4=%d v6=%d)" % (len(v4), len(v6)))
    return r.get("etag", ""), v4, v6


def render(etag, v4, v6):
    out = ['n8n_public_edge_cloudflare_ips_etag: "%s"' % etag,
           "n8n_public_edge_cloudflare_ipv4:"]
    out += ["  - %s" % c for c in v4]
    out.append("n8n_public_edge_cloudflare_ipv6:")
    # Quoted: a bare IPv6 CIDR starts with a digit and contains colons, which
    # YAML can read as a sexagesimal/mapping rather than a string.
    out += ['  - "%s"' % c for c in v6]
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="apply the change in place")
    args = ap.parse_args()

    etag, v4, v6 = fetch()
    new_block = render(etag, v4, v6)
    text = DEFAULTS.read_text()

    # Line-based, not a regex. A non-greedy regex anchored on the etag key
    # stops at the NEXT key - which is the ipv4 list - so it silently rewrote
    # the etag alone and left stale ranges behind while reporting success.
    lines = text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines)
                     if l.startswith("n8n_public_edge_cloudflare_ips_etag:"))
        v6_key = next(i for i, l in enumerate(lines)
                      if l.startswith("n8n_public_edge_cloudflare_ipv6:"))
    except StopIteration:
        raise SystemExit("could not locate the vendored range block in %s" % DEFAULTS)
    end = v6_key + 1
    while end < len(lines) and lines[end].startswith("  - "):
        end += 1
    if v6_key < start:
        raise SystemExit("unexpected key order in %s" % DEFAULTS)

    updated = "\n".join(lines[:start] + new_block.rstrip("\n").split("\n") + lines[end:]) + "\n"

    if updated == text:
        print("up to date (etag %s, %d v4, %d v6)" % (etag, len(v4), len(v6)))
        return 0
    if not args.write:
        print("WOULD CHANGE (etag %s, %d v4, %d v6). Re-run with --write." % (etag, len(v4), len(v6)))
        return 1
    DEFAULTS.write_text(updated)
    print("updated %s (etag %s, %d v4, %d v6)" % (DEFAULTS, etag, len(v4), len(v6)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
