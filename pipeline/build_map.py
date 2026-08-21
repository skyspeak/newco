#!/usr/bin/env python3
"""Stages 4-8: scrub -> similarity -> cluster -> wedge analytics -> out/map.json

Similarity is a blend of five views of "what the firm does". No single view is
trusted: canonical tags are precise but sparse, tokens are noisy but dense, and
function mix / delivery mode capture shape rather than subject matter.

Clustering is average-linkage agglomerative on cosine distance, implemented directly
(no sklearn in this environment). Clusters are NAMED AFTER the fact from the tags
that are most over-represented inside them -- never assigned from a code list.
"""
import json, re, math, collections, pathlib, itertools, sys
from datetime import date
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from privacy import scrub

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"

W = {"tags": 0.32, "tag_tokens": 0.18, "stmt_tokens": 0.22, "families": 0.18, "mode": 0.10}
K_CLUSTERS = 10
KNN = 6

# ---------------------------------------------------------------- vectorizing
def idf_matrix(docs, min_df=1):
    """docs: list of dict(term->count). Returns (L2-normalized tf-idf matrix, vocab)."""
    df = collections.Counter(t for d in docs for t in d)
    vocab = sorted(t for t, c in df.items() if c >= min_df)
    vi = {t: i for i, t in enumerate(vocab)}
    n = len(docs)
    M = np.zeros((n, len(vocab)), dtype=np.float32)
    for i, d in enumerate(docs):
        for t, c in d.items():
            j = vi.get(t)
            if j is None:
                continue
            M[i, j] = (1.0 + math.log(c)) * math.log((1.0 + n) / (1.0 + df[t])) + 1e-6
    nrm = np.linalg.norm(M, axis=1, keepdims=True)
    nrm[nrm == 0] = 1.0
    return M / nrm, vocab

def cos(M):
    S = M @ M.T
    np.fill_diagonal(S, 1.0)
    return np.clip(S, 0.0, 1.0)

# ---------------------------------------------------------------- clustering
def agglomerative(S, k):
    """Average-linkage agglomerative clustering on similarity matrix S."""
    n = S.shape[0]
    clusters = {i: [i] for i in range(n)}
    sim = {}
    for a, b in itertools.combinations(range(n), 2):
        sim[(a, b)] = float(S[a, b])
    active = set(range(n))
    nxt = n
    while len(active) > k:
        best, bs = None, -1.0
        for (a, b), v in sim.items():
            if a in active and b in active and v > bs:
                best, bs = (a, b), v
        if best is None:
            break
        a, b = best
        merged = clusters[a] + clusters[b]
        active.discard(a); active.discard(b)
        cid = nxt; nxt += 1
        clusters[cid] = merged
        for c in list(active):
            mem_c = clusters[c]
            v = float(np.mean(S[np.ix_(merged, mem_c)]))
            sim[(min(c, cid), max(c, cid))] = v
        active.add(cid)
        sim = {kk: vv for kk, vv in sim.items() if kk[0] in active and kk[1] in active}
    return [clusters[c] for c in sorted(active, key=lambda c: -len(clusters[c]))]

def label_tokens(labels):
    out = set()
    for l in labels:
        for w in re.findall(r"[a-z]{3,}", (l or "").lower()):
            if w not in {"and", "the", "services", "service", "other", "general"}:
                out.add(w)
    return out

# ---------------------------------------------------------------- main
def main():
    recs = json.loads((OUT / "normalized.json").read_text())
    n = len(recs)

    viol = scrub(recs)
    (OUT / "scrub_report.json").write_text(json.dumps(viol, indent=1))
    print(f"scrub: {len(viol)} flagged item(s) across {n} records")
    for v in viol[:12]:
        print(f"   [{v['kind']}] {v['slug']}: {v['match']}")

    # --- five views
    Mtag, tag_vocab = idf_matrix([{t: 1 for t in r["capability_tags"]} for r in recs])
    Mtok, _ = idf_matrix([r["tag_tokens"] for r in recs], min_df=2)
    Mstm, _ = idf_matrix([r["stmt_tokens"] for r in recs], min_df=2)
    Mfam, fam_vocab = idf_matrix([{k: max(1, int(v * 100)) for k, v in r["function_mix"].items()} for r in recs])
    Mmod, _ = idf_matrix([{**{f"vc-{v}": 1 for v in r["value_chain"]},
                           **{f"dm-{v}": 1 for v in r["delivery_mode"]}} for r in recs])

    S = (W["tags"] * cos(Mtag) + W["tag_tokens"] * cos(Mtok) + W["stmt_tokens"] * cos(Mstm)
         + W["families"] * cos(Mfam) + W["mode"] * cos(Mmod))
    np.fill_diagonal(S, 1.0)

    # Two sectors per firm, deliberately kept apart:
    #   sector_claimed -- derived from the index's own industry label (what the world says)
    #   sector_actual  -- derived from the firm's extracted capabilities (what it does)
    # Neither is used to BUILD the map. Their disagreement is itself a finding: it is
    # the misclassification rate of the incumbent labelling system, measured directly.
    from sectors import sector_from_labels, sector_from_tags
    for r in recs:
        r["sector_claimed"] = sector_from_labels(r["index_industry_labels"]) or "unclassified"
        r["sector_actual"] = sector_from_tags(r["capability_tags"])
        r["sector"] = r["sector_actual"]
        r["sector_mismatch"] = (r["sector_claimed"] != "unclassified"
                                and r["sector_claimed"] != r["sector_actual"])

    # --- clusters (over-cluster, then absorb runt clusters into their nearest neighbour)
    groups = agglomerative(S, K_CLUSTERS + 3)
    MIN_CLUSTER = 4
    big = [g for g in groups if len(g) >= MIN_CLUSTER]
    runts = [g for g in groups if len(g) < MIN_CLUSTER]
    for g in runts:
        for i in g:
            best = max(range(len(big)), key=lambda bi: float(np.mean(S[i, big[bi]])))
            big[best].append(i)
    groups = sorted(big, key=lambda g: -len(g))
    cluster_of = {}
    for ci, g in enumerate(groups):
        for i in g:
            cluster_of[i] = ci
    print(f"clustering: {len(runts)} runt cluster(s) absorbed -> {len(groups)} final clusters")

    # name clusters by tag lift (over-representation inside vs corpus)
    global_tag = collections.Counter(t for r in recs for t in r["capability_tags"])
    clusters = []
    for ci, g in enumerate(groups):
        inside = collections.Counter(t for i in g for t in recs[i]["capability_tags"])
        lift = []
        for t, c in inside.items():
            if c < 2:
                continue
            p_in = c / len(g)
            p_all = global_tag[t] / n
            lift.append((p_in / max(p_all, 1e-9), c, t))
        lift.sort(reverse=True)
        sig = [t for _, _, t in lift[:9]]
        if not sig:  # tiny/absorbed cluster: fall back to most common tags present
            sig = [t for t, _ in inside.most_common(6)]
        fams = collections.Counter()
        for i in g:
            for k, v in recs[i]["function_mix"].items():
                fams[k] += v
        vc = collections.Counter(v for i in g for v in recs[i]["value_chain"])
        dm = collections.Counter(v for i in g for v in recs[i]["delivery_mode"])
        # index labels present in this activity cluster -- the "how many industries
        # got mixed together" number, which is the anti-DUNS headline
        labs = collections.Counter(l for i in g for l in recs[i]["index_industry_labels"])
        clusters.append({
            "id": ci,
            "size": len(g),
            "members": [recs[i]["slug"] for i in g],
            "signature_tags": sig,
            "top_families": [k for k, _ in fams.most_common(5)],
            "value_chain": [k for k, _ in vc.most_common(3)],
            "delivery_mode": [k for k, _ in dm.most_common(3)],
            "distinct_index_labels": len(labs),
            "sector_mix": dict(collections.Counter(recs[i]["sector"] for i in g).most_common()),
            "index_labels": [l for l, _ in labs.most_common(8)],
            "mean_internal_sim": round(float(np.mean(S[np.ix_(g, g)])), 3),
        })

    # --- tag sector entropy: how PORTABLE is a capability?
    # "drug-development" lives in one sector (entropy 0) -- it is subject matter.
    # "regulatory-compliance-ops" spans many (entropy high) -- it is work shape.
    # This single measure lets us separate two things that look identical in a naive
    # twin test: mislabeled peers vs genuinely cross-domain work overlap.
    n_sectors = len({r["sector"] for r in recs})
    tag_entropy = {}
    for t in global_tag:
        holders = collections.Counter(recs[i]["sector"] for i in range(n)
                                      if t in recs[i]["capability_tags"])
        tot = sum(holders.values())
        if tot <= 1:
            tag_entropy[t] = 0.0
            continue
        h = -sum((c / tot) * math.log(c / tot) for c in holders.values())
        tag_entropy[t] = h / math.log(min(n_sectors, tot)) if min(n_sectors, tot) > 1 else 0.0

    PORTABLE = {t for t, e in tag_entropy.items() if e >= 0.55}

    # --- OPERATIONAL similarity: work SHAPE only, subject matter stripped out.
    # Uses function mix, value-chain/delivery mode, and only the portable capabilities.
    # This is what surfaces "a hospital system and an airline run the same kind of
    # operation" -- invisible to any classification built on what a firm sells.
    Mport, _ = idf_matrix([{t: 1 for t in r["capability_tags"] if t in PORTABLE} for r in recs])
    S_op = 0.45 * cos(Mfam) + 0.25 * cos(Mmod) + 0.30 * cos(Mport)
    np.fill_diagonal(S_op, 1.0)

    # --- WEDGE 1: activity twins
    # A twin must cross a COARSE SECTOR boundary, not merely differ in label wording.
    # Ranked, not thresholded: absolute similarity is not comparable across a sparse
    # tag space, but the ranking of cross-sector pairs is meaningful.
    twins = []
    for a, b in itertools.combinations(range(n), 2):
        s = float(S[a, b])
        if s < 0.22:
            continue
        sa, sb = recs[a]["sector"], recs[b]["sector"]
        if sa != sb and "unclassified" not in (sa, sb):
            shared = sorted(set(recs[a]["capability_tags"]) & set(recs[b]["capability_tags"]))
            shared_fam = sorted(set(recs[a]["function_mix"]) & set(recs[b]["function_mix"]))
            twins.append({
                "a": recs[a]["slug"], "a_name": recs[a]["company"],
                "b": recs[b]["slug"], "b_name": recs[b]["company"],
                "similarity": round(s, 3),
                "a_label": "; ".join(recs[a]["index_industry_labels"][:2]) or "(no label)",
                "b_label": "; ".join(recs[b]["index_industry_labels"][:2]) or "(no label)",
                "a_sector": sa, "b_sector": sb,
                "shared_tags": shared[:8], "n_shared_tags": len(shared),
                "shared_families": shared_fam[:6],
                "same_cluster": cluster_of[a] == cluster_of[b],
                "shared_tag_entropy": round(
                    float(np.mean([tag_entropy.get(t, 0.0) for t in shared])) if shared else 0.0, 3),
                "op_similarity": round(float(S_op[a, b]), 3),
            })
    # A pair sharing only LOW-entropy (sector-bound) capabilities is not a cross-domain
    # twin -- it is two firms in the same business that the indexes labeled differently.
    for t in twins:
        t["kind"] = "mislabeled_peer" if t["shared_tag_entropy"] < 0.35 and t["n_shared_tags"] >= 2 \
                    else "cross_domain"
    twins.sort(key=lambda x: -x["similarity"])

    # operational twins: ranked on WORK SHAPE across sector boundaries
    op_twins = []
    for a, b in itertools.combinations(range(n), 2):
        sa, sb = recs[a]["sector_actual"], recs[b]["sector_actual"]
        if sa == sb or "unclassified" in (sa, sb):
            continue
        v = float(S_op[a, b])
        if v < 0.35:
            continue
        shared_all = set(recs[a]["capability_tags"]) & set(recs[b]["capability_tags"])
        # if the pair shares ANY sector-bound subject capability, they are in the same
        # business and one of them is simply mislabeled -- not a cross-domain twin
        if any(tag_entropy.get(t, 0.0) < 0.35 for t in shared_all):
            continue
        shared_port = sorted(shared_all & PORTABLE)
        shared_fam = sorted(set(recs[a]["function_mix"]) & set(recs[b]["function_mix"]))
        subject_overlap = len(set(recs[a]["capability_tags"]) & set(recs[b]["capability_tags"]) - PORTABLE)
        op_twins.append({
            "a": recs[a]["slug"], "a_name": recs[a]["company"], "a_sector": sa,
            "b": recs[b]["slug"], "b_name": recs[b]["company"], "b_sector": sb,
            "a_label": "; ".join(recs[a]["index_industry_labels"][:2]) or "(no label)",
            "b_label": "; ".join(recs[b]["index_industry_labels"][:2]) or "(no label)",
            "op_similarity": round(v, 3),
            "subject_similarity": round(float(S[a, b]), 3),
            "shared_portable_capabilities": shared_port[:6],
            "shared_families": shared_fam[:6],
            "shared_value_chain": sorted(set(recs[a]["value_chain"]) & set(recs[b]["value_chain"])),
            "shared_delivery_mode": sorted(set(recs[a]["delivery_mode"]) & set(recs[b]["delivery_mode"])),
            "subject_tag_overlap": subject_overlap,
        })
    # the interesting ones do the same KIND of work while selling different things
    op_twins.sort(key=lambda x: -(x["op_similarity"] - 0.5 * x["subject_similarity"]))

    # --- WEDGE 2: hidden employers
    # Every extractor wrote SOMETHING in name_reality_gap, so prose alone selects
    # 147/147 and means nothing. We score it instead, from three measurable signals:
    #   foreign_tag_share -- share of the firm's capabilities whose MODAL holder sits
    #                        in a different sector (its activity is borrowed)
    #   tech_staffing     -- software/data/hardware share of function mix
    #   cross_sector_nbrs -- share of its 6 nearest activity neighbours in other sectors
    tag_sector_mode = {}
    for t in global_tag:
        holders = [recs[i]["sector"] for i in range(n) if t in recs[i]["capability_tags"]]
        if holders:
            tag_sector_mode[t] = collections.Counter(holders).most_common(1)[0][0]

    hidden = []
    for i, r in enumerate(recs):
        tags = r["capability_tags"]
        foreign = [t for t in tags if tag_sector_mode.get(t, r["sector"]) != r["sector"]]
        foreign_share = len(foreign) / max(len(tags), 1)
        swt = sum(v for k, v in r["function_mix"].items()
                  if k in {"software-engineering", "data-and-analytics", "hardware-engineering"})
        nbrs = [int(j) for j in np.argsort(-S[i])[1:7]]
        xsec = sum(1 for j in nbrs if recs[j]["sector"] != r["sector"]) / max(len(nbrs), 1)
        label_is_tech = r["sector"] == "technology"
        score = 0.45 * foreign_share + 0.35 * (swt if not label_is_tech else 0.0) + 0.20 * xsec
        gap = (r.get("name_reality_gap") or "").strip()
        hidden.append({
            "slug": r["slug"], "company": r["company"],
            "index_label": "; ".join(r["index_industry_labels"][:2]) or "(no label)",
            "sector": r["sector"],
            "hidden_score": round(score, 3),
            "foreign_tag_share": round(foreign_share, 3),
            "foreign_tags": foreign[:6],
            "tech_staffing_share": round(swt, 3),
            "cross_sector_neighbor_share": round(xsec, 3),
            "label_is_tech": label_is_tech,
            "name_reality_gap": gap if gap.lower() not in {"none", "none.", "n/a"} else "",
            "cluster": cluster_of[i],
            "n_segments": len(r["segments"]),
        })
    hidden.sort(key=lambda x: -x["hidden_score"])

    # --- WEDGE 4: adjacency ladders (Dijkstra over the kNN activity graph)
    adj = collections.defaultdict(dict)
    for i in range(n):
        order = np.argsort(-S[i])
        for j in order[1:KNN + 1]:
            j = int(j)
            w = 1.0 - float(S[i, j])
            adj[i][j] = min(adj[i].get(j, 9), w)
            adj[j][i] = min(adj[j].get(i, 9), w)

    def path(src, dst):
        import heapq
        dist = {src: 0.0}; prev = {}; pq = [(0.0, src)]; seen = set()
        while pq:
            d, u = heapq.heappop(pq)
            if u in seen:
                continue
            seen.add(u)
            if u == dst:
                break
            for v, w in adj[u].items():
                nd = d + w
                if nd < dist.get(v, 1e9):
                    dist[v] = nd; prev[v] = u; heapq.heappush(pq, (nd, v))
        if dst not in dist:
            return None
        out, cur = [dst], dst
        while cur != src:
            cur = prev[cur]; out.append(cur)
        return list(reversed(out))

    # ladders between the most activity-distant cluster pairs
    cent = {}
    for c in clusters:
        idx = [i for i in range(n) if cluster_of[i] == c["id"]]
        cent[c["id"]] = idx
    pairs = []
    for c1, c2 in itertools.combinations(cent, 2):
        v = float(np.mean(S[np.ix_(cent[c1], cent[c2])]))
        pairs.append((v, c1, c2))
    pairs.sort()
    ladders = []
    for v, c1, c2 in pairs[:14]:
        a = max(cent[c1], key=lambda i: float(np.mean(S[i, cent[c1]])))
        b = max(cent[c2], key=lambda i: float(np.mean(S[i, cent[c2]])))
        p = path(a, b)
        if p and 3 <= len(p) <= 8:
            steps = []
            for x, y in zip(p, p[1:]):
                sh = sorted(set(recs[x]["capability_tags"]) & set(recs[y]["capability_tags"]))
                if not sh:
                    sh = sorted(set(recs[x]["tag_tokens"]) & set(recs[y]["tag_tokens"]))[:3]
                steps.append({"from": recs[x]["company"], "to": recs[y]["company"],
                              "similarity": round(float(S[x, y]), 3), "via": sh[:4]})
            ladders.append({"from_cluster": c1, "to_cluster": c2,
                            "cross_cluster_sim": round(v, 3),
                            "chain": [recs[i]["company"] for i in p], "steps": steps})
    ladders.sort(key=lambda l: -len(l["chain"]))

    # --- WEDGE 2b: label mismatch register (the incumbent system's error rate)
    mismatches = [{
        "slug": r["slug"], "company": r["company"],
        "index_label": "; ".join(r["index_industry_labels"][:2]) or "(no label)",
        "sector_claimed": r["sector_claimed"], "sector_actual": r["sector_actual"],
        "evidence_tags": [t for t in r["capability_tags"]][:6],
        "name_reality_gap": r["name_reality_gap"],
        "cluster": cluster_of[i],
    } for i, r in enumerate(recs) if r["sector_mismatch"]]
    mismatch_pairs = collections.Counter(
        (m["sector_claimed"], m["sector_actual"]) for m in mismatches)

    # --- WEDGE 6: activity concentration
    conc = []
    for t, c in global_tag.items():
        if c >= 1:
            holders = [recs[i]["company"] for i in range(n) if t in recs[i]["capability_tags"]]
            conc.append({"tag": t, "n_firms": c, "firms": holders[:8],
                         "n_clusters": len({cluster_of[i] for i in range(n)
                                            if t in recs[i]["capability_tags"]})})
    conc.sort(key=lambda x: (-x["n_firms"], x["tag"]))
    scarce = [c for c in conc if 2 <= c["n_firms"] <= 3]

    # --- structural stats + seed bias
    idx_counts = collections.Counter(s["index"] for r in recs for s in r["seed_indexes"])
    fam_share = collections.Counter()
    for r in recs:
        for k, v in r["function_mix"].items():
            fam_share[k] += v
    sw_firms = [r["company"] for r in recs if r["function_mix"].get("software-engineering", 0) >= 0.2]
    nontech_sw = [h for h in hidden if not h["label_is_tech"] and h["tech_staffing_share"] >= 0.25]
    sector_counts = collections.Counter(r["sector"] for r in recs)
    # how badly do sectors shatter across activity clusters, and vice versa?
    sector_spread = {}
    for sec in sector_counts:
        idx = [i for i in range(n) if recs[i]["sector"] == sec]
        sector_spread[sec] = len({cluster_of[i] for i in idx})

    stats = {
        "n_companies": n,
        "n_activity_statements": sum(r["n_statements"] for r in recs),
        "n_canonical_tags": len(global_tag),
        "n_tags_shared": sum(1 for v in global_tag.values() if v >= 2),
        "n_distinct_index_labels": len({l for r in recs for l in r["index_industry_labels"]}),
        "n_firms_with_segments": sum(1 for r in recs if r["segments"]),
        "mean_extraction_confidence": round(
            float(np.mean([r["extraction_confidence"] or 0 for r in recs])), 3),
        "rows_per_index": dict(idx_counts),
        "multi_index_firms": sum(1 for r in recs if r["index_count"] >= 2),
        "n_twins": len(twins),
        "n_twins_cross_cluster": sum(1 for t in twins if not t["same_cluster"]),
        "n_twins_mislabeled_peer": sum(1 for t in twins if t["kind"] == "mislabeled_peer"),
        "n_twins_cross_domain": sum(1 for t in twins if t["kind"] == "cross_domain"),
        "n_op_twins": len(op_twins),
        "n_portable_capabilities": len(PORTABLE),
        "n_hidden": len(hidden),
        "n_nontech_label_tech_staffing": len(nontech_sw),
        "software_staffing_firms_20pct": len(sw_firms),
        "top_families": [[k, round(v / n, 3)] for k, v in fam_share.most_common(12)],
        "scarce_capabilities": len(scarce),
        "mean_pairwise_similarity": round(float((S.sum() - n) / (n * n - n)), 3),
        "sector_counts": dict(sector_counts.most_common()),
        "n_sector_mismatch": len(mismatches),
        "sector_mismatch_rate": round(len(mismatches) / n, 3),
        "n_labeled_firms": sum(1 for r in recs if r["sector_claimed"] != "unclassified"),
        "top_mismatch_flows": [{"from": k[0], "to": k[1], "n": v}
                               for k, v in mismatch_pairs.most_common(10)],
        "sector_cluster_spread": sector_spread,
        "mean_foreign_tag_share": round(float(np.mean([h["foreign_tag_share"] for h in hidden])), 3),
    }

    payload = {
        "generated": date.today().isoformat(),
        "stats": stats,
        "clusters": clusters,
        "companies": [{
            "slug": r["slug"], "company": r["company"], "domain": r["domain"],
            "cluster": cluster_of[i],
            "sector": r["sector_actual"],
            "sector_claimed": r["sector_claimed"],
            "sector_mismatch": r["sector_mismatch"],
            "index_labels": r["index_industry_labels"],
            "seed_indexes": sorted({s["index"] for s in r["seed_indexes"]}),
            "index_count": r["index_count"],
            "tags": r["capability_tags"],
            "families": r["function_mix"],
            "value_chain": r["value_chain"], "delivery_mode": r["delivery_mode"],
            "statements": r["activity_statements"],
            "n_segments": len(r["segments"]),
            "segments": [{"name": s.get("name"), "weight": s.get("weight")} for s in r["segments"]][:6],
            "name_reality_gap": r["name_reality_gap"],
            "confidence": r["extraction_confidence"],
            "n_sources": len([s for s in r["sources"] if (s or {}).get("url")]),
            "neighbors": [{"slug": recs[int(j)]["slug"], "company": recs[int(j)]["company"],
                           "sim": round(float(S[i, int(j)]), 3)}
                          for j in np.argsort(-S[i])[1:7]],
        } for i, r in enumerate(recs)],
        "twins": twins[:70],
        "op_twins": op_twins[:40],
        "portable_capabilities": sorted(
            [{"tag": t, "entropy": round(tag_entropy[t], 3), "n_firms": global_tag[t]}
             for t in PORTABLE if global_tag[t] >= 3], key=lambda x: -x["n_firms"])[:30],
        "hidden_employers": hidden[:70],
        "ladders": ladders[:8],
        "sector_mismatches": mismatches,
        "concentration_common": conc[:25],
        "concentration_scarce": scarce[:30],
        "scrub_violations": viol,
    }
    (OUT / "map.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
    np.save(OUT / "similarity.npy", S)

    print(f"\nclusters (k={K_CLUSTERS}):")
    for c in clusters:
        print(f"  [{c['id']}] n={c['size']:3d} labels={c['distinct_index_labels']:2d} "
              f"sim={c['mean_internal_sim']} :: {', '.join(c['signature_tags'][:5])}")
    print(f"\nsubject twins: {len(twins)} "
          f"({sum(1 for t in twins if t['kind']=='mislabeled_peer')} mislabeled peers, "
          f"{sum(1 for t in twins if t['kind']=='cross_domain')} cross-domain)")
    for t in [x for x in twins if x["kind"] == "mislabeled_peer"][:5]:
        print(f"  MISLABEL {t['similarity']}  {t['a_name']} [{t['a_label']}] <> {t['b_name']} [{t['b_label']}]")
    print(f"\nportable capabilities (work shape, not subject): {len(PORTABLE)}")
    print(f"\nOPERATIONAL twins (same work shape, different industry): {len(op_twins)}")
    for t in op_twins[:12]:
        print(f"  op={t['op_similarity']} subj={t['subject_similarity']}  "
              f"{t['a_name']} [{t['a_sector']}] <> {t['b_name']} [{t['b_sector']}]")
        print(f"      via: {', '.join(t['shared_portable_capabilities'][:3]) or '-'} | "
              f"fams: {', '.join(t['shared_families'][:3])}")
    print(f"\ntop hidden employers by score:")
    for h in hidden[:10]:
        print(f"  {h['hidden_score']}  {h['company']:28s} [{h['sector']:22s}] foreign={h['foreign_tag_share']} tech={h['tech_staffing_share']}")
    print(f"\nlabel mismatch: {len(mismatches)}/{sum(1 for r in recs if r['sector_claimed'] != 'unclassified')} labeled firms sit in a sector their activity contradicts")
    for k, v in mismatch_pairs.most_common(6):
        print(f"   {v:3d}  filed as {k[0]:24s} -> actually {k[1]}")
    print(f"\nsector -> distinct activity clusters it lands in:")
    for sec, sp in sorted(sector_spread.items(), key=lambda x: -x[1])[:8]:
        print(f"  {sec:32s} {sp} clusters (n={sector_counts[sec]})")
    print(f"ladders: {len(ladders)}, scarce capabilities: {len(scarce)}")
    print(f"\nwrote {OUT/'map.json'}")

if __name__ == "__main__":
    main()
