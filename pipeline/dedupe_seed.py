#!/usr/bin/env python3
"""Stage 1: canonicalize the composite seed into one row per company.

Input : seed/seed_raw.csv   (one row per company x source_index)
Output: seed/companies.json (one record per distinct company, with index provenance)

Inclusion is NOT decided here -- this stage only establishes the seed frontier and
records how each company entered. Index labels are preserved verbatim so we can later
measure how badly they describe actual activity.
"""
import csv, json, re, sys, collections, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "seed" / "seed_raw.csv"
OUT = ROOT / "seed" / "companies.json"

# name variants that refer to the same operating reality in our seed
ALIASES = {
    "jpmorgan chase": "JPMorganChase",
    "jpmorganchase": "JPMorganChase",
    "jp morgan chase": "JPMorganChase",
    "alphabet": "Google (Alphabet)",
    "alphabet inc.": "Google (Alphabet)",
    "google": "Google (Alphabet)",
    "in-n-out": "In-N-Out Burger",
    "in-n-out burger": "In-N-Out Burger",
    "cvs health": "CVS Health",
    "at&t": "AT&T",
    "the baldwin group": "Baldwin Group",
}

def slugify(name: str) -> str:
    s = name.lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")

def canon(name: str) -> str:
    key = name.strip().lower().rstrip(".,")
    key = re.sub(r"\s+", " ", key)
    if key in ALIASES:
        return ALIASES[key]
    # strip trailing corporate suffixes for matching purposes only
    stripped = re.sub(r"\b(inc|inc\.|corp|corp\.|corporation|company|co|llc|ltd|plc|group|holdings)\b\.?$",
                      "", key).strip()
    if stripped in ALIASES:
        return ALIASES[stripped]
    return name.strip().rstrip(".,")

def main():
    if not RAW.exists():
        sys.exit(f"missing {RAW}")
    rows = list(csv.DictReader(RAW.open(encoding="utf-8")))
    by_company = collections.OrderedDict()

    for r in rows:
        raw_name = (r.get("company") or "").strip()
        if not raw_name:
            continue
        name = canon(raw_name)
        slug = slugify(name)
        rec = by_company.setdefault(slug, {
            "slug": slug,
            "company": name,
            "domain": "",
            "seed_indexes": [],
            "index_industry_labels": [],
            "hq_location": "",
            "name_variants": set(),
        })
        rec["name_variants"].add(raw_name)
        dom = (r.get("domain") or "").strip().lower()
        if dom and not rec["domain"]:
            rec["domain"] = dom
        hq = (r.get("hq_location") or "").strip()
        if hq and not rec["hq_location"]:
            rec["hq_location"] = hq
        idx = (r.get("source_index") or "").strip()
        rank = (r.get("rank_or_rating") or "").strip()
        if idx:
            rec["seed_indexes"].append({
                "index": idx,
                "rank_or_rating": rank,
                "source_url": (r.get("source_url") or "").strip(),
            })
        lab = (r.get("index_industry_label") or "").strip()
        if lab and lab not in rec["index_industry_labels"]:
            rec["index_industry_labels"].append(lab)

    out = []
    for rec in by_company.values():
        rec["name_variants"] = sorted(rec["name_variants"])
        rec["index_count"] = len({s["index"] for s in rec["seed_indexes"]})
        out.append(rec)

    # multi-index companies first: they are the densest part of the seed frontier
    out.sort(key=lambda r: (-r["index_count"], r["company"].lower()))
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")

    idx_counts = collections.Counter(s["index"] for r in out for s in r["seed_indexes"])
    print(f"rows in            : {len(rows)}")
    print(f"distinct companies : {len(out)}")
    print(f"missing domain     : {sum(1 for r in out if not r['domain'])}")
    print(f"on >=2 indexes     : {sum(1 for r in out if r['index_count'] >= 2)}")
    print(f"on >=3 indexes     : {sum(1 for r in out if r['index_count'] >= 3)}")
    print("\nrows per index:")
    for k, v in idx_counts.most_common():
        print(f"  {k:42s} {v}")
    print("\ndistinct index_industry_labels:",
          len({l for r in out for l in r["index_industry_labels"]}))
    print(f"\nwrote {OUT}")

if __name__ == "__main__":
    main()
