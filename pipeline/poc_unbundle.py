#!/usr/bin/env python3
"""Proof of concept: the unit of analysis is a line of work, not a ticker.

Builds two graphs with the SAME similarity (canonical tags + tag tokens):
  firm graph     — one node per company (the status quo)
  line graph     — conglomerates exploded into segments; everyone else a firm

Then writes out/poc_unbundle.html: before/after neighbors, smear scores, and
an inverted capability search over the line graph.

Writes out/lines.json so later stages (the newco bridge) match against
line-of-work nodes instead of smeared tickers. Also writes the before/after
PoC page. If map.json is present, smear stats are folded into it for orgmap.
"""
import json, glob, collections, pathlib, sys
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from normalize import canon_tag, _slug as slugify
from build_map import idf_matrix, cos
from unbundle import explode_profile, firm_node, token_counts

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
KNN = 6
W_TAG, W_TOK = 0.65, 0.35

SHOWCASE = [
    "amazon", "microsoft", "google-alphabet", "apple",
    "the-walt-disney-company", "comcast", "sony",
    "cvs-health", "unitedhealth-group", "jpmorganchase",
]

INVERT = [
    "cloud-infrastructure-services",
    "cloud-infrastructure",
    "fulfillment-network",
    "fulfillment-and-last-mile",
    "theme-park-operations",
    "pharmacy-benefit-management",
    "clinical-care-delivery",
    "ad-inventory-marketplace",
    "semiconductor-fabrication",
    "investment-banking",
    "gaming-platform-operations",
]


def load_profiles():
    files = sorted(glob.glob(str(ROOT / "profiles" / "*.json")))
    recs = []
    pass1 = collections.Counter()
    for f in files:
        d = json.load(open(f))
        recs.append(d)
        for t in d.get("capability_tags") or []:
            s = slugify(t)
            pass1[s] += 1
        for seg in d.get("segments") or []:
            for t in seg.get("capability_tags") or []:
                s = slugify(t)
                pass1[s] += 1
    corpus = {t for t, c in pass1.items() if c >= 1}
    return recs, corpus


def similarity(nodes):
    Mtag, _ = idf_matrix([{t: 1 for t in n["capability_tags"]} for n in nodes])
    Mtok, _ = idf_matrix([token_counts(n["capability_tags"]) for n in nodes], min_df=1)
    S = W_TAG * cos(Mtag) + W_TOK * cos(Mtok)
    np.fill_diagonal(S, 1.0)
    return S


def knn(S, i, nodes, k=KNN, skip_parent=None):
    order = np.argsort(-S[i])
    out = []
    for j in order:
        j = int(j)
        if j == i:
            continue
        other = nodes[j]
        if skip_parent and other["parent"] == skip_parent:
            continue
        shared = sorted(set(nodes[i]["capability_tags"]) & set(other["capability_tags"]))
        out.append({
            "id": other["id"],
            "name": other["name"],
            "parent": other["parent"],
            "parent_name": other["parent_name"],
            "kind": other["kind"],
            "sim": round(float(S[i, j]), 3),
            "shared": shared[:6],
        })
        if len(out) >= k:
            break
    return out


def smear(bundled_nbrs, line_nbrs):
    a = {n["parent"] for n in bundled_nbrs}
    b = {n["parent"] for n in line_nbrs}
    if not a and not b:
        return 0.0
    return round(1.0 - len(a & b) / len(a | b), 3)


def invert_hits(nodes, S, tag, k=10):
    hits = []
    for i, n in enumerate(nodes):
        if tag not in n["capability_tags"]:
            continue
        hits.append({
            "id": n["id"],
            "name": n["name"],
            "parent": n["parent"],
            "kind": n["kind"],
            "weight": n.get("weight"),
            "tags": n["capability_tags"][:8],
            "neighbors": knn(S, i, nodes, k=4, skip_parent=n["parent"]),
        })
    hits.sort(key=lambda h: (-(h["weight"] or 0), h["name"]))
    return hits[:k]


def compact_node(n):
    return {
        "id": n["id"], "name": n["name"], "kind": n["kind"],
        "parent": n["parent"], "parent_name": n["parent_name"],
        "segment": n.get("segment"), "weight": n.get("weight"),
        "tags": n["capability_tags"][:10],
    }


def main():
    recs, corpus = load_profiles()
    by_slug = {r["slug"]: r for r in recs if r.get("slug")}

    firm_nodes = [firm_node(r, canon_tag, corpus) for r in recs]
    line_nodes = []
    for r in recs:
        line_nodes.extend(explode_profile(r, canon_tag, corpus))

    Sf = similarity(firm_nodes)
    Sl = similarity(line_nodes)
    firm_ix = {n["id"]: i for i, n in enumerate(firm_nodes)}
    line_ix = {n["id"]: i for i, n in enumerate(line_nodes)}

    n_split = sum(1 for n in line_nodes if n["kind"] == "segment")
    n_parents = len({n["parent"] for n in line_nodes if n["kind"] == "segment"})

    showcases = []
    for slug in SHOWCASE:
        if slug not in firm_ix:
            continue
        fi = firm_ix[slug]
        bundled = knn(Sf, fi, firm_nodes, skip_parent=None)
        lines = [n for n in line_nodes if n["parent"] == slug]
        line_payload = []
        union_nbrs = []
        for n in lines:
            li = line_ix[n["id"]]
            nbrs = knn(Sl, li, line_nodes, skip_parent=n["parent"])
            siblings = knn(Sl, li, line_nodes, k=4, skip_parent=None)
            siblings = [s for s in siblings if s["parent"] == n["parent"]]
            union_nbrs.extend(nbrs)
            line_payload.append({
                **compact_node(n),
                "neighbors": nbrs,
                "siblings": siblings,
            })
        showcases.append({
            "slug": slug,
            "company": firm_nodes[fi]["name"],
            "n_lines": len(lines),
            "smear": smear(bundled, union_nbrs) if len(lines) > 1 else 0.0,
            "bundled_tags": firm_nodes[fi]["capability_tags"][:12],
            "bundled": bundled,
            "lines": line_payload,
        })

    invert = []
    tag_set = {t for n in line_nodes for t in n["capability_tags"]}
    for tag in INVERT:
        if tag not in tag_set:
            # try unsynonymed form already in corpus
            continue
        invert.append({"tag": tag, "hits": invert_hits(line_nodes, Sl, tag)})

    stats = {
        "n_firms": len(firm_nodes),
        "n_line_nodes": len(line_nodes),
        "n_segment_nodes": n_split,
        "n_split_parents": n_parents,
        "similarity": "0.65 canonical tags + 0.35 tag tokens",
        "knn": KNN,
    }

    payload = {"stats": stats, "showcases": showcases, "invert": invert}
    OUT.mkdir(exist_ok=True)
    (OUT / "poc_unbundle.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")

    lines_out = {
        "stats": stats,
        "nodes": [{
            "id": n["id"], "name": n["name"], "kind": n["kind"],
            "parent": n["parent"], "parent_name": n["parent_name"],
            "segment": n.get("segment"), "weight": n.get("weight"),
            "tags": n["capability_tags"],
        } for n in line_nodes],
    }
    (OUT / "lines.json").write_text(json.dumps(lines_out, indent=1), encoding="utf-8")

    map_path = OUT / "map.json"
    if map_path.exists():
        m = json.loads(map_path.read_text(encoding="utf-8"))
        m.setdefault("stats", {})
        m["stats"]["n_line_nodes"] = stats["n_line_nodes"]
        m["stats"]["n_segment_nodes"] = stats["n_segment_nodes"]
        m["stats"]["n_split_parents"] = stats["n_split_parents"]
        m["unbundle"] = [{
            "n": s["company"], "smear": s["smear"], "lines": s["n_lines"],
        } for s in showcases]
        map_path.write_text(json.dumps(m, indent=1), encoding="utf-8")

    tpl = (ROOT / "pipeline" / "poc_template.html").read_text(encoding="utf-8")
    html = tpl.replace("/*__DATA__*/", json.dumps(payload, separators=(",", ":")))
    (OUT / "poc_unbundle.html").write_text(html, encoding="utf-8")

    print(f"firms                 : {stats['n_firms']}")
    print(f"line-of-work nodes    : {stats['n_line_nodes']}")
    print(f"segment nodes         : {stats['n_segment_nodes']} from {stats['n_split_parents']} parents")
    print("\nsmear (1 = bundled neighborhood disagrees with split):")
    for s in showcases:
        print(f"  {s['smear']:.3f}  {s['company']:28s}  {s['n_lines']} lines")
        if s["lines"]:
            top = s["lines"][0]
            nbr = ", ".join(n["name"] for n in top["neighbors"][:3]) or "—"
            print(f"           e.g. {top['name']} → {nbr}")
    print(f"\nwrote {OUT / 'lines.json'} ({len(line_nodes)} nodes)")
    print(f"wrote {OUT / 'poc_unbundle.html'}")


if __name__ == "__main__":
    main()
