#!/usr/bin/env python3
"""Place newly incorporated firms next to incumbents that already do that work.

The seed is yesterday's hot-list employers. The newco file is a 2025–26
incorporation cohort (YC W26 and peers), tagged in the *same* capability
vocabulary. A cable exists when two firms share at least two canonical tags.
One overlapping word is not a desk. YC industry strings are a label, not an edge.

Writes:
  out/map.json          (newcos + stats, in place)
  out/poc_bridge.json
  out/poc_bridge.html
"""
import json, glob, pathlib, sys, statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
sys.path.insert(0, str(ROOT / "pipeline"))
from normalize import canon_tag, _slug
from merge_expansion import cluster_tag_bags, assign_cluster
from privacy import find_violations
from gen_page import cluster_name

KNN = 5
CABLES = 3  # cables drawn per newco on the shore diagram
MIN_SHARED = 2  # one shared tag is a vocabulary coincidence, not a desk


def canon_list(tags):
    out, seen = [], set()
    for t in tags or []:
        ct = canon_tag(t) or _slug(t)
        if ct and ct not in seen:
            seen.add(ct)
            out.append(ct)
    return out


def jaccard(a, b):
    A, B = set(a), set(b)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def bridge_score(new_tags, inc_tags, same_cluster):
    """Overlap first. Jaccard alone punishes a two-tag newco against a 12-tag incumbent."""
    shared = sorted(set(new_tags) & set(inc_tags))
    if not shared:
        return 0.0, []
    j = jaccard(new_tags, inc_tags)
    cover = len(shared) / max(len(new_tags), 1)
    s = 0.55 * j + 0.45 * cover
    if same_cluster:
        s += 0.06
    return round(s, 3), shared


def load_lines():
    p = OUT / "lines.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data.get("nodes") or []
    return data if isinstance(data, list) else []


def incumbents(m, line_nodes=None):
    """Prefer exploded line-of-work nodes. Fall back to smeared ticker tags."""
    cluster_of = {c["slug"]: c["cluster"] for c in m["companies"]}
    rows = []
    if line_nodes:
        for n in line_nodes:
            tags = canon_list(n.get("tags") or [])
            if not tags:
                continue
            parent = n.get("parent") or n.get("id")
            kind = "line" if n.get("kind") == "segment" else "seed"
            rows.append({
                "slug": n.get("id") or parent,
                "name": n.get("name") or parent,
                "kind": kind,
                "parent": parent,
                "cluster": cluster_of.get(parent),
                "tags": tags,
            })
    else:
        for c in m["companies"]:
            rows.append({
                "slug": c["slug"],
                "name": c["company"],
                "kind": "seed",
                "parent": c["slug"],
                "cluster": c["cluster"],
                "tags": canon_list(c.get("tags") or []),
            })
    for i, r in enumerate(m.get("expansion") or []):
        rows.append({
            "slug": "off-" + str(i),
            "name": r["company"],
            "kind": "off",
            "parent": "off-" + str(i),
            "cluster": r["cluster"],
            "tags": canon_list(r.get("matched_capabilities") or []),
        })
    return rows


def neighbors_for(tags, cluster, pool, k=KNN):
    scored = []
    for inc in pool:
        s, shared = bridge_score(tags, inc["tags"], inc.get("cluster") == cluster)
        if s <= 0 or len(shared) < MIN_SHARED:
            continue
        scored.append({
            "slug": inc["slug"],
            "name": inc["name"],
            "kind": inc["kind"],
            "parent": inc.get("parent") or inc["slug"],
            "cluster": inc.get("cluster"),
            "sim": s,
            "shared": shared[:6],
        })
    scored.sort(key=lambda x: (-x["sim"], x["name"]))
    listed = [x for x in scored if x["kind"] in ("seed", "line")]
    off = [x for x in scored if x["kind"] == "off"]
    picked, seen, parents = [], set(), {}

    def take(x):
        if x["slug"] in seen:
            return False
        p = x.get("parent") or x["slug"]
        if parents.get(p, 0) >= 2:
            return False
        picked.append(x)
        seen.add(x["slug"])
        parents[p] = parents.get(p, 0) + 1
        return len(picked) >= k

    for src in (listed[: max(3, k - 1)], scored, off):
        for x in src:
            if take(x):
                return picked
    return picked


def count_desk_hits(kept):
    """A desk hit is a nearest neighbor that is a named line inside a split ticker."""
    n = 0
    for row in kept:
        top = (row.get("neighbors") or [None])[0]
        if top and top.get("kind") == "line":
            n += 1
    return n


def load_newcos():
    files = sorted(glob.glob(str(ROOT / "newcos" / "*.json")))
    rows = []
    for f in files:
        data = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise SystemExit(f"{f}: expected a list")
        rows.extend(data)
    return rows


def scrub_row(r):
    rec = {
        "company": r.get("company"),
        "activity_statements": [r.get("activity_evidence") or "", r.get("bridge") or ""],
        "source_url": r.get("source_url"),
    }
    return find_violations(rec)


def main():
    m = json.loads((OUT / "map.json").read_text(encoding="utf-8"))
    bags = cluster_tag_bags(m)
    line_nodes = load_lines()
    pool = incumbents(m, line_nodes)
    names = {c["id"]: cluster_name(c) for c in m["clusters"]}
    used_lines = bool(line_nodes)

    raw = load_newcos()
    kept, dropped = [], {}
    seen = set()
    for r in raw:
        name = (r.get("company") or "").strip()
        if not name:
            dropped["no_name"] = dropped.get("no_name", 0) + 1
            continue
        key = _slug(name)
        if key in seen:
            dropped["duplicate"] = dropped.get("duplicate", 0) + 1
            continue
        if float(r.get("confidence") or 0) < 0.7:
            dropped["low_confidence"] = dropped.get("low_confidence", 0) + 1
            continue
        if not (r.get("activity_evidence") or "").strip() or not (r.get("source_url") or "").strip():
            dropped["no_evidence_or_source"] = dropped.get("no_evidence_or_source", 0) + 1
            continue
        viol = scrub_row(r)
        if any(v["kind"] in ("email", "phone", "person") for v in viol):
            dropped["privacy"] = dropped.get("privacy", 0) + 1
            print(f"  !! privacy drop {name}: {viol}")
            continue
        tags = canon_list(r.get("matched_capabilities") or [])
        if not tags:
            dropped["no_tags"] = dropped.get("no_tags", 0) + 1
            continue
        cid = assign_cluster(tags, bags, fallback=None)
        if cid is None:
            dropped["no_cluster"] = dropped.get("no_cluster", 0) + 1
            continue
        seen.add(key)
        nbrs = neighbors_for(tags, cid, pool)
        if not nbrs:
            # Line nodes drop leftover parent tags on purpose. If no line
            # shares work, fall back to the smeared ticker so a newco is
            # not orphaned (Condor vs Chevron's leftover energy-trading tags).
            nbrs = neighbors_for(tags, cid, incumbents(m, None))
        kept.append({
            "slug": key,
            "company": name,
            "domain": r.get("domain") or "",
            "founded": r.get("founded"),
            "batch": r.get("batch") or "",
            "yc_label": r.get("yc_label") or "",
            "cluster": cid,
            "cluster_name": names.get(cid, f"Cluster {cid}"),
            "matched_capabilities": tags,
            "activity_evidence": r["activity_evidence"].strip(),
            "bridge": (r.get("bridge") or "").strip(),
            "source_url": r["source_url"].strip(),
            "confidence": round(float(r.get("confidence") or 0), 2),
            "neighbors": nbrs,
        })

    cables = []
    shared_lens = []
    shore_ids = set()
    for n in kept:
        for nb in n["neighbors"][:CABLES]:
            cables.append({
                "from": n["slug"],
                "to": nb["slug"],
                "sim": nb["sim"],
                "shared": nb["shared"],
                "cluster": n["cluster"],
            })
            shared_lens.append(len(nb["shared"]))
            shore_ids.add(nb["slug"])

    by_slug = {p["slug"]: p for p in pool}
    shore = []
    for sid in shore_ids:
        p = by_slug.get(sid)
        if not p:
            continue
        shore.append({
            "slug": p["slug"], "name": p["name"], "kind": p["kind"],
            "parent": p.get("parent"),
            "cluster": p["cluster"], "cluster_name": names.get(p["cluster"], ""),
        })
    shore.sort(key=lambda x: (x["cluster"], x["name"]))

    n_label_drift = sum(1 for n in kept if n["yc_label"] and n["cluster_name"]
                        and n["yc_label"].split("/")[0].strip().lower()
                        not in n["cluster_name"].lower())
    n_desk = count_desk_hits(kept)

    stats = {
        "n_newcos": len(kept),
        "n_bridge_cables": len(cables),
        "n_incumbents_on_shore": len(shore),
        "median_shared_tags": round(statistics.median(shared_lens), 2) if shared_lens else 0,
        "n_yc_label_drift": n_label_drift,
        "n_desk_hits": n_desk,
        "dropped": dropped,
        "knn": KNN,
        "score": "0.55 Jaccard + 0.45 newco-tag coverage; +0.06 same cluster",
        "min_shared": MIN_SHARED,
        "cohort": "YC W26 / founded 2024–2026, firm-level sources only",
        "incumbent_unit": "line-of-work node" if used_lines else "ticker",
        "n_line_nodes": len(line_nodes),
    }

    m["newcos"] = kept
    m["stats"]["n_newcos"] = stats["n_newcos"]
    m["stats"]["n_bridge_cables"] = stats["n_bridge_cables"]
    m["stats"]["n_yc_label_drift"] = n_label_drift
    m["stats"]["n_desk_hits"] = n_desk
    (OUT / "map.json").write_text(json.dumps(m, indent=1), encoding="utf-8")

    payload = {
        "stats": stats,
        "clusters": [{"id": c["id"], "name": names[c["id"]]} for c in m["clusters"]],
        "newcos": kept,
        "shore": shore,
        "cables": cables,
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "poc_bridge.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
    tpl = (ROOT / "pipeline" / "bridge_template.html").read_text(encoding="utf-8")
    html = tpl.replace("/*__DATA__*/", json.dumps(payload, separators=(",", ":")))
    (OUT / "poc_bridge.html").write_text(html, encoding="utf-8")

    print(f"newcos kept          : {len(kept)}")
    print(f"incumbent unit       : {stats['incumbent_unit']} ({len(line_nodes)} line nodes)")
    print(f"cables (top {CABLES}/firm): {len(cables)}")
    print(f"incumbents on shore  : {len(shore)}")
    print(f"median shared tags   : {stats['median_shared_tags']}")
    print(f"YC label ≠ cluster   : {n_label_drift}/{len(kept)}")
    print(f"attach to a desk     : {n_desk}/{len(kept)}  (nearest neighbor is a named line)")
    print(f"dropped              : {dropped or '{}'}")
    print("\nbridges:")
    for n in kept:
        top = n["neighbors"][0] if n["neighbors"] else None
        via = ", ".join((top or {}).get("shared") or [])[:60]
        who = top["name"] if top else "—"
        print(f"  {n['company']:22s} → {who:28s}  {n['cluster_name']}")
        if via:
            print(f"           via {via}")
    print(f"\nwrote {OUT / 'poc_bridge.html'}")


if __name__ == "__main__":
    main()
