#!/usr/bin/env python3
"""Stage 2: validate raw profiles against the activity-profile contract.

This is the gate between extraction (human/agent-written JSON) and the map.
Hard failures abort the pipeline. Soft warnings print and continue — partial
records are allowed; fabricated or person-level records are not.
"""
import json, glob, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from privacy import find_violations

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROFILES = ROOT / "profiles"
SEED = ROOT / "seed" / "companies.json"

REQUIRED = (
    "slug", "company", "domain", "activity_statements", "capability_tags",
    "function_mix", "value_chain", "delivery_mode", "name_reality_gap",
    "sources", "extraction_confidence",
)
VALUE_CHAIN = {"research", "design", "manufacture", "distribute", "operate", "service", "assure"}
DELIVERY_MODE = {"software", "physical-asset", "human-service", "marketplace", "content", "advisory"}
SOURCE_KINDS = {
    "about-page", "what-we-do", "product-page", "careers-page",
    "10k-item1", "segment-reporting", "engineering-blog", "newsroom", "other",
}


def load_profiles():
    files = sorted(PROFILES.glob("*.json"))
    recs = []
    errors = []
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append({"slug": f.stem, "kind": "invalid_json", "match": str(e)})
            continue
        d["_path"] = f.name
        recs.append(d)
    return recs, errors


def validate_one(d: dict) -> tuple:
    hard, soft = [], []
    slug = d.get("slug") or pathlib.Path(d.get("_path", "")).stem
    fname = d.get("_path", "")

    for k in REQUIRED:
        if k not in d or d[k] in (None, ""):
            hard.append({"slug": slug, "kind": f"missing_{k}", "match": ""})

    if fname and d.get("slug") and fname != f"{d['slug']}.json":
        hard.append({"slug": slug, "kind": "slug_filename_mismatch",
                     "match": f"{fname} vs {d.get('slug')}"})

    stmts = d.get("activity_statements") or []
    if not isinstance(stmts, list):
        hard.append({"slug": slug, "kind": "activity_statements_not_list", "match": ""})
        stmts = []
    for i, a in enumerate(stmts):
        if not isinstance(a, dict) or not (a.get("statement") or "").strip():
            hard.append({"slug": slug, "kind": "empty_statement", "match": str(i)})
            continue
        if not (a.get("source_url") or "").strip():
            hard.append({"slug": slug, "kind": "statement_missing_source", "match": str(i)})
    if 0 < len(stmts) < 5:
        soft.append({"slug": slug, "kind": "few_statements", "match": str(len(stmts))})

    tags = d.get("capability_tags") or []
    if not isinstance(tags, list) or not tags:
        hard.append({"slug": slug, "kind": "no_capability_tags", "match": ""})
    elif len(tags) < 6:
        soft.append({"slug": slug, "kind": "few_tags", "match": str(len(tags))})

    fam = d.get("function_mix") or []
    if not isinstance(fam, list) or not fam:
        hard.append({"slug": slug, "kind": "no_function_mix", "match": ""})
    else:
        total = 0.0
        for fm in fam:
            if not isinstance(fm, dict) or not fm.get("family"):
                hard.append({"slug": slug, "kind": "bad_function_mix_row", "match": ""})
                continue
            try:
                total += float(fm.get("weight") or 0)
            except (TypeError, ValueError):
                hard.append({"slug": slug, "kind": "bad_function_mix_weight", "match": str(fm)})
        if fam and not (0.5 <= total <= 1.5):
            soft.append({"slug": slug, "kind": "function_mix_not_normalized",
                         "match": f"sum={total:.2f}"})

    vc = [str(v).lower() for v in (d.get("value_chain") or [])]
    dm = [str(v).lower() for v in (d.get("delivery_mode") or [])]
    if not vc:
        hard.append({"slug": slug, "kind": "empty_value_chain", "match": ""})
    for v in vc:
        if v in VALUE_CHAIN:
            continue
        if v in DELIVERY_MODE:
            soft.append({"slug": slug, "kind": "value_chain_looks_like_delivery_mode", "match": v})
        else:
            hard.append({"slug": slug, "kind": "invalid_value_chain", "match": v})
    if not dm:
        hard.append({"slug": slug, "kind": "empty_delivery_mode", "match": ""})
    for v in dm:
        if v in DELIVERY_MODE:
            continue
        if v in VALUE_CHAIN:
            soft.append({"slug": slug, "kind": "delivery_mode_looks_like_value_chain", "match": v})
        else:
            hard.append({"slug": slug, "kind": "invalid_delivery_mode", "match": v})

    sources = d.get("sources") or []
    if not isinstance(sources, list) or not any((s or {}).get("url") for s in sources if isinstance(s, dict)):
        hard.append({"slug": slug, "kind": "no_provenance", "match": ""})
    for s in sources:
        if isinstance(s, dict) and s.get("kind") and s["kind"] not in SOURCE_KINDS:
            soft.append({"slug": slug, "kind": "unknown_source_kind", "match": str(s.get("kind"))})

    conf = d.get("extraction_confidence")
    try:
        cf = float(conf)
        if not (0.0 <= cf <= 1.0):
            hard.append({"slug": slug, "kind": "confidence_out_of_range", "match": str(conf)})
        elif cf < 0.5:
            soft.append({"slug": slug, "kind": "low_confidence", "match": str(cf)})
    except (TypeError, ValueError):
        hard.append({"slug": slug, "kind": "bad_confidence", "match": str(conf)})

    gap = (d.get("name_reality_gap") or "").strip()
    if not gap:
        soft.append({"slug": slug, "kind": "empty_name_reality_gap", "match": ""})

    # privacy + provenance regex pass (person/email/phone); skip duplicate no_provenance
    for v in find_violations(d):
        if v["kind"] == "no_provenance":
            continue
        hard.append(v)

    return hard, soft


def main(argv=None) -> int:
    recs, load_err = load_profiles()
    hard, soft = list(load_err), []
    for d in recs:
        h, s = validate_one(d)
        hard.extend(h)
        soft.extend(s)

    seed_slugs = set()
    if SEED.exists():
        seed_slugs = {r["slug"] for r in json.loads(SEED.read_text(encoding="utf-8"))}
        profile_slugs = {d.get("slug") for d in recs}
        for slug in sorted(seed_slugs - profile_slugs):
            hard.append({"slug": slug, "kind": "seed_missing_profile", "match": ""})
        for slug in sorted(profile_slugs - seed_slugs):
            soft.append({"slug": slug, "kind": "profile_not_in_seed", "match": ""})

    print(f"profiles           : {len(recs)}")
    print(f"seed companies     : {len(seed_slugs) or '(no seed yet)'}")
    print(f"hard failures      : {len(hard)}")
    print(f"warnings           : {len(soft)}")
    for v in hard[:40]:
        print(f"  FAIL [{v['kind']}] {v['slug']}: {v['match']}")
    if len(hard) > 40:
        print(f"  ... {len(hard) - 40} more")
    for v in soft[:20]:
        print(f"  warn [{v['kind']}] {v['slug']}: {v['match']}")
    if len(soft) > 20:
        print(f"  ... {len(soft) - 20} more")

    (ROOT / "out").mkdir(exist_ok=True)
    (ROOT / "out" / "validate_report.json").write_text(
        json.dumps({"hard": hard, "soft": soft}, indent=1), encoding="utf-8")

    if hard:
        print(f"\nvalidate FAILED — {len(hard)} hard error(s), see out/validate_report.json")
        return 1
    print("\nvalidate OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
