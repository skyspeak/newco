#!/usr/bin/env python3
"""Stage 9: fold the off-index expansion into the map and quantify the seed's bias.

The seed came from employer-brand rankings, so it over-represents large firms with a
consumer identity. The expansion set is the corrective: firms verified to perform the
same activities that appear on NONE of the 2026 indexes.

Expansion files are named cluster_N.json from the clustering at search time. Integer
cluster ids reshuffle, so each firm is assigned to the *current* cluster whose member
tags overlap its matched capabilities. The filename is only a fallback.
"""
import json, glob, pathlib, collections, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
sys.path.insert(0, str(ROOT / "pipeline"))
from normalize import canon_tag, _slug


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def cluster_tag_bags(m):
    """Weighted tag bags per current cluster: member tags + boosted signatures."""
    by_slug = {c["slug"]: c for c in m["companies"]}
    bags = {}
    for c in m["clusters"]:
        bag = collections.Counter()
        for slug in c.get("members") or []:
            firm = by_slug.get(slug) or {}
            for t in firm.get("tags") or []:
                ct = canon_tag(t)
                if ct:
                    bag[ct] += 1
        for t in c.get("signature_tags") or []:
            ct = canon_tag(t)
            if ct:
                bag[ct] += 8
        bags[c["id"]] = bag
    return bags


def assign_cluster(caps, bags, fallback=None):
    """Score capability overlap against current cluster tag bags."""
    tags = []
    for t in caps or []:
        ct = canon_tag(t) or _slug(t)
        if ct:
            tags.append(ct)
    if not tags or not bags:
        return fallback
    # Exclusive signature tags are a hard vote: a firm tagged
    # theme-park-operations belongs in that cluster even if it also
    # carries a portable tag like revenue-management.
    exclusive = {}
    for cid, bag in bags.items():
        for t, w in bag.items():
            if w >= 8:  # signature boost
                exclusive.setdefault(t, set()).add(cid)
    exclusive = {t: next(iter(cids)) for t, cids in exclusive.items() if len(cids) == 1}

    scores = {}
    for cid, bag in bags.items():
        scores[cid] = sum(bag.get(t, 0) for t in tags)
    for t in tags:
        if t in exclusive:
            scores[exclusive[t]] = scores.get(exclusive[t], 0) + 40
    best = max(scores, key=scores.get)
    if scores[best] <= 0:
        return fallback
    return best


def load_expansion_rows():
    files = sorted(glob.glob(str(ROOT / "expansion" / "*.json")))
    rows, errors = [], []
    for f in files:
        m = re.search(r"cluster_(\d+)", pathlib.Path(f).name)
        file_cid = int(m.group(1)) if m else None
        try:
            data = json.load(open(f))
        except Exception as e:
            errors.append(f"{f}: {e}")
            continue
        if not isinstance(data, list):
            errors.append(f"{f}: expected a list")
            continue
        for r in data:
            rows.append((file_cid, r))
    return rows, errors


def main():
    m = json.loads((OUT / "map.json").read_text())
    seed_names = {norm(c["company"]) for c in m["companies"]}
    seed_domains = {norm(c.get("domain", "")) for c in m["companies"] if c.get("domain")}
    bags = cluster_tag_bags(m)

    raw, errors = load_expansion_rows()
    for e in errors:
        print(f"  !! {e}")

    rows, dropped = [], collections.Counter()
    seen = set()
    reassigned = 0
    for file_cid, r in raw:
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
        cid = assign_cluster(r.get("matched_capabilities") or [], bags, fallback=file_cid)
        if cid is None:
            dropped["no_cluster"] += 1
            continue
        if r.get("cluster") not in (None, cid) or file_cid != cid:
            reassigned += 1
        seen.add(key)
        rows.append({
            "company": name,
            "domain": r.get("domain", ""),
            "cluster": cid,
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
            "search_capped": True,
        })

    m["expansion"] = rows
    m["expansion_coverage"] = coverage
    m["stats"]["n_off_index"] = len(rows)
    m["stats"]["n_total_firms"] = len(m["companies"]) + len(rows)
    m["stats"]["expansion_dropped"] = dict(dropped)
    m["stats"]["expansion_reassigned"] = reassigned
    m["stats"]["expansion_search_cap_note"] = (
        "Off-index firms are assigned to current activity clusters by capability "
        "overlap. Counts are an existence proof, not a population estimate.")
    (OUT / "map.json").write_text(json.dumps(m, indent=1), encoding="utf-8")

    print(f"off-index firms kept : {len(rows)}")
    print(f"reassigned to current clusters : {reassigned}")
    print(f"dropped              : {dict(dropped)}")
    print(f"total firms in map   : {m['stats']['n_total_firms']}")

    print("\nper cluster (on-index vs off-index found):")
    for c in coverage:
        print(f"  [{c['cluster']}] on={c['on_index']:3d} off={c['off_index_found']:3d}"
              f"  :: {', '.join(c['signature'][:3])}")


if __name__ == "__main__":
    main()
