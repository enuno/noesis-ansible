#!/usr/bin/env python3
"""expected_profiles.py — derive the expected live profile set for a fleet
from its declared roster file. Used by roles/hermes_profiles validate.yml
(A5: the same hermes_profiles_fleets var drives configure and validate).

Usage:
  expected_profiles.py <roster.yaml> <noesis|agency> <mode> <want-csv|-> [maps]

  roster.yaml  fleet roster (profiles/noesis-roster.yaml or
               agency/.scratch/roster.yaml in the bundle)
  mode         all | wave1 | waveN  — must match what configure applied
  want         comma-separated profile filter (empty/'-' = no filter)
  maps         (noesis only) honor maps_to; core maps to the default profile

Output: YAML list of expected live profile names on stdout.
"""
import sys

import yaml


def main() -> int:
    roster_path, fleet, mode = sys.argv[1], sys.argv[2], sys.argv[3]
    want = [w for w in (sys.argv[4] if len(sys.argv) > 4 else "-").split(",") if w and w != "-"]
    data = yaml.safe_load(open(roster_path, encoding="utf-8"))
    out = []

    if fleet == "noesis":
        wave_num = mode.replace("wave", "") if mode.startswith("wave") else None
        for name, p in (data.get("profiles") or {}).items():
            if wave_num and mode != "all" and str(p.get("wave", "")) != wave_num:
                continue
            live = p.get("maps_to") or name
            out.append(str(live))
    elif fleet == "agency":
        wave_num = mode.replace("wave", "") if mode.startswith("wave") else None
        for p in (data.get("profiles") or []):
            if wave_num and mode != "all" and str(p.get("wave", "")) != wave_num:
                continue
            out.append(str(p.get("name")))
    else:
        print(f"unknown fleet type: {fleet}", file=sys.stderr)
        return 2

    if want:
        norm = {w if w.startswith("agency-") else f"agency-{w}" for w in want} \
            if fleet == "agency" else set(want)
        out = [n for n in out if n in norm or n.replace("agency-", "") in norm]

    yaml.safe_dump(sorted(set(out)), sys.stdout, default_flow_style=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
