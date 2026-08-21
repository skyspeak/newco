#!/usr/bin/env python3
"""Stage 9: fold the off-index expansion into the map and quantify the seed's bias.

The seed came from employer-brand rankings, so it over-represents large firms with a
consumer identity. The expansion set is the corrective: firms verified to perform the
same activities that appear on NONE of the 2026 indexes. The ratio between them is the
honest measure of how much of an activity's real employer base a "hot list" shows you.
"""
import json, glob, pathlib, collections, re

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"

def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())

def main():
    m = json.loads((OUT / "map.json").read_text())
    seed_names = {norm(c["company"]) for c in m["companies"]}
    seed_domains = {norm(c.get("domain", "")) for c in m["companies"] if c.get("domain")}

    rows, dropped = [], collections.Counter()
    seen = set()
    for f in sorted(glob.glob(str(ROOT / "expansion" / "cluster_*.json"))):
        cid = int(re.search(r"cluster_(\d+)", f).group(1))
        try:
            data = json.load(open(f))
        except Exception as e:
            print(f"  !! {f}: {e}")
            continue
        for r in data:
            name = (r.get("company") or "").strip()
            if not name:
                dropped["no_name"] += 1
                continue
            key = norm(name)
            dom = norm(r.get("domain", ""))
            if key in seed_names or (dom and dom in seed_domains):
                dropped["already_on_index"] += 1
                continue
            if key in seen:
                dropped["duplicate"] += 1
                continue
            if float(r.get("confidence") or 0) < 0.7:
                dropped["low_confidence"] += 1
                continue
            if not (r.get("activity_evidence") or "").strip() or not (r.get("source_url") or "").strip():
                dropped["no_evidence_or_source"] += 1
                continue
            seen.add(key)
            rows.append({
                "company": name,
                "domain": r.get("domain", ""),
                "cluster": r.get("cluster", cid),
                "matched_capabilities": r.get("matched_capabilities", [])[:6],
                "activity_evidence": r["activity_evidence"].strip(),
                "why_off_index": (r.get("why_off_index") or "").strip(),
                "source_url": r["source_url"].strip(),
                "confidence": round(float(r.get("confidence") or 0), 2),
            })

    per_cluster = collections.Counter(r["cluster"] for r in rows)
    cl = {c["id"]: c for c in m["clusters"]}
    coverage = []
    for cid, c in sorted(cl.items()):
        off = per_cluster.get(cid, 0)
        on = c["size"]
        coverage.append({
            "cluster": cid,
            "signature": c["signature_tags"][:4],
            "on_index": on,
            "off_index_found": off,
            # NOTE: deliberately NO ratio here. Each cluster was searched to the same
            # 10-14 candidate cap, so any "share visible" figure would measure the
            # search budget, not the real employer base. These counts are an EXISTENCE
            # PROOF (off-index firms doing this work exist and can be named), not an
            # estimate of how many there are.
            "search_capped": True,
        })

    m["expansion"] = rows
    m["expansion_coverage"] = coverage
    m["stats"]["n_off_index"] = len(rows)
    m["stats"]["n_total_firms"] = len(m["companies"]) + len(rows)
    m["stats"]["expansion_dropped"] = dict(dropped)
    m["stats"]["expansion_search_cap_note"] = (
        "Off-index counts are search-capped at 10-14 candidates per cluster and are an "
        "existence proof, not a population estimate.")
    (OUT / "map.json").write_text(json.dumps(m, indent=1), encoding="utf-8")

    print(f"off-index firms kept : {len(rows)}")
    print(f"dropped              : {dict(dropped)}")
    print(f"total firms in map   : {m['stats']['n_total_firms']}")

    print("\nper cluster (on-index vs off-index found):")
    for c in coverage:
        print(f"  [{c['cluster']}] on={c['on_index']:3d} off={c['off_index_found']:3d} (capped)"
              f"  :: {', '.join(c['signature'][:3])}")

if __name__ == "__main__":
    main()
