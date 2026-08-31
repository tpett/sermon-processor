#!/usr/bin/env python3
"""Where we stand against the target: 80% of weeks needing no boundary edit."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parent.parent / "data"
TOL = (0.5, 1, 2, 5, 10)

rows = [json.loads(l) for l in open(DATA / "results.jsonl")]
by = defaultdict(list)
for r in rows:
    if r.get("true_in") is not None:
        by[r["config_id"]].append(r)

print("Punch-in and punch-out measured separately, then together.")
print("'both' is the no-edit proxy: found, and both boundaries inside tolerance.\n")
hdr = f"{'config':<28}{'found':>7}" + "".join(f"{'in≤'+str(t):>8}" for t in TOL)
print(hdr); print("-" * len(hdr))
for cfg, rs in sorted(by.items()):
    f = [r for r in rs if r["found"]]
    cells = "".join(f"{100*sum(1 for r in f if abs(r['punch_in_error'])<=t)/len(rs):7.0f}%" for t in TOL)
    print(f"{cfg[:27]:<28}{100*len(f)/len(rs):6.0f}%{cells}")

print()
hdr2 = f"{'config':<28}{'':>7}" + "".join(f"{'out≤'+str(t):>8}" for t in TOL)
print(hdr2); print("-" * len(hdr2))
for cfg, rs in sorted(by.items()):
    f = [r for r in rs if r["found"]]
    cells = "".join(f"{100*sum(1 for r in f if abs(r['punch_out_error'])<=t)/len(rs):7.0f}%" for t in TOL)
    print(f"{cfg[:27]:<28}{'':>7}{cells}")

print()
hdr3 = f"{'config':<28}{'':>7}" + "".join(f"{'both≤'+str(t):>9}" for t in TOL)
print(hdr3); print("-" * len(hdr3))
for cfg, rs in sorted(by.items()):
    f = [r for r in rs if r["found"]]
    cells = "".join(
        f"{100*sum(1 for r in f if abs(r['punch_in_error'])<=t and abs(r['punch_out_error'])<=t)/len(rs):8.0f}%"
        for t in TOL)
    print(f"{cfg[:27]:<28}{'':>7}{cells}")

print("\n--- what is actually blocking, best config ---")
best = max(by, key=lambda c: sum(1 for r in by[c] if r["found"]
                                 and abs(r["punch_in_error"]) <= 5
                                 and abs(r["punch_out_error"]) <= 5))
rs = by[best]
print(f"{best}  (n={len(rs)})")
for r in sorted(rs, key=lambda x: x["desktop_label"]):
    if not r["found"]:
        print(f"  {r['desktop_label'][:33]:<35} SEGMENT NOT FOUND")
        continue
    i, o = r["punch_in_error"], r["punch_out_error"]
    verdict = ("ok" if abs(i) <= 5 and abs(o) <= 5
               else "punch-in needs a nudge" if abs(o) <= 5
               else "punch-out needs a nudge" if abs(i) <= 5 else "both off")
    print(f"  {r['desktop_label'][:33]:<35}in {i:+8.2f}s  out {o:+8.2f}s   {verdict}")
oi = [abs(r["punch_in_error"]) for r in rs if r["found"]]
oo = [abs(r["punch_out_error"]) for r in rs if r["found"]]
orc_i = [r["oracle_in"] for r in rs]
print(f"\n  punch-in  median {np.median(oi):6.2f}s   oracle {np.median(orc_i):.2f}s")
print(f"  punch-out median {np.median(oo):6.2f}s")
