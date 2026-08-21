#!/usr/bin/env python3
"""Stage 3: normalize extracted profiles into a comparable feature space.

The extractors produced an emergent vocabulary on purpose (1,097 tags, 928 of them
used exactly once). Raw tags alone are too sparse to form edges, so we normalize on
three levels rather than forcing tags onto a code list:

  1. canonical tag   -- rule-based suffix stripping + a synonym table
  2. tag tokens      -- tags shattered into words, so "cold-chain-logistics" and
                        "logistics-network-operations" still share "logistics"
  3. statement tokens-- content words from the activity statements themselves

Level 1 gives precision, levels 2-3 give recall. Similarity blends all three.
"""
import json, glob, re, collections, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]

# suffixes that add no distinguishing meaning to a capability tag.
# Longer forms first so "-operations" is not eaten by "-ops".
SUFFIXES = ["-operations", "-operation", "-management", "-services", "-service",
            "-solutions", "-platform", "-systems", "-programs", "-program", "-mgmt", "-ops"]

# synonym table: variants that are genuinely the same capability
SYNONYMS = {
    "loyalty-program": "loyalty-programs",
    "loyalty-program-management": "loyalty-programs",
    "customer-loyalty": "loyalty-programs",
    "clinical-care": "clinical-care-delivery",
    "patient-care-delivery": "clinical-care-delivery",
    "acute-care-delivery": "clinical-care-delivery",
    "hospital": "hospital-operations",
    "inpatient-care": "hospital-operations",
    "cybersecurity": "cybersecurity-services",
    "cyber-security": "cybersecurity-services",
    "information-security": "cybersecurity-services",
    "regulatory-compliance": "regulatory-compliance-ops",
    "compliance": "regulatory-compliance-ops",
    "regulatory-affairs": "regulatory-compliance-ops",
    "e-commerce": "e-commerce-operations",
    "ecommerce": "e-commerce-operations",
    "digital-commerce": "e-commerce-operations",
    "online-retail": "e-commerce-operations",
    "omni-channel-retail": "omnichannel-retail",
    "omnichannel-retailing": "omnichannel-retail",
    "retail-store": "retail-store-operations",
    "brick-and-mortar-retail": "retail-store-operations",
    "logistics": "logistics-network",
    "distribution-network": "logistics-network",
    "freight-transport": "logistics-network",
    "last-mile-delivery": "last-mile-delivery",
    "fulfillment": "fulfillment-network",
    "fulfillment-and-last-mile": "fulfillment-network",
    "e-commerce-fulfillment": "fulfillment-network",
    "warehouse": "warehouse-operations",
    "warehousing": "warehouse-operations",
    "cloud-infrastructure": "cloud-infrastructure-services",
    "cloud": "cloud-infrastructure-services",
    "public-cloud": "cloud-infrastructure-services",
    "software-development": "software-engineering",
    "saas": "subscription-saas",
    "software-as-a-service": "subscription-saas",
    "machine-learning": "ai-and-machine-learning",
    "artificial-intelligence": "ai-and-machine-learning",
    "ai-research": "ai-and-machine-learning",
    "ai-model-development": "ai-and-machine-learning",
    "large-language-model-development": "ai-and-machine-learning",
    "generative-ai": "ai-and-machine-learning",
    "data-analytics": "data-and-analytics",
    "analytics": "data-and-analytics",
    "underwriting": "insurance-underwriting",
    "risk-underwriting": "insurance-underwriting",
    "claims-processing": "claims-adjudication",
    "claims": "claims-adjudication",
    "lending": "consumer-lending",
    "credit-underwriting": "consumer-lending",
    "asset-management": "institutional-asset-management",
    "investment-management": "institutional-asset-management",
    "drug-development": "pharmaceutical-drug-development",
    "drug-discovery": "pharmaceutical-drug-development",
    "clinical-trials": "clinical-trial-operations",
    "semiconductor-manufacturing": "semiconductor-fabrication",
    "chip-fabrication": "semiconductor-fabrication",
    "chip-design": "semiconductor-design",
    "field-service": "field-service-technicians",
    "field-services": "field-service-technicians",
    "field-technicians": "field-service-technicians",
    "franchise": "franchise-licensing",
    "franchising": "franchise-licensing",
    "digital-advertising": "ad-inventory-marketplace",
    "advertising-marketplace": "ad-inventory-marketplace",
    "retail-media": "ad-inventory-marketplace",
    "advertising-sales": "ad-inventory-marketplace",
    "consulting": "management-consulting",
    "advisory": "management-consulting",
    "strategy-consulting": "management-consulting",
    "payments": "payment-processing",
    "payment-network": "payment-network-operations",
    "call-center": "contact-center-operations",
    "customer-support": "contact-center-operations",
    "contact-center": "contact-center-operations",
    "24x7-operations": "24x7-noc",
    "network-operations-center": "24x7-noc",
    "manufacturing": "discrete-manufacturing",
    "contract-manufacturing": "outsourced-manufacturing",
    "supply-chain": "supply-chain-management",
    "sourcing": "supply-chain-management",
    "procurement": "supply-chain-management",
}

# function-family normalization (families arrived with many near-duplicates)
FAMILY_SYNONYMS = {
    "software-engineering-and-technology": "software-engineering",
    "engineering-and-technology": "software-engineering",
    "technology": "software-engineering",
    "software-development": "software-engineering",
    "product-and-engineering": "software-engineering",
    "corporate-and-support": "corporate-and-administrative",
    "corporate-functions": "corporate-and-administrative",
    "finance-and-corporate": "finance-and-accounting",
    "finance-and-operations": "finance-and-accounting",
    "finance": "finance-and-accounting",
    "supply-chain": "supply-chain-and-logistics",
    "supply-chain-and-sourcing": "supply-chain-and-logistics",
    "logistics": "supply-chain-and-logistics",
    "commercial-and-sales": "sales-and-marketing",
    "marketing-and-brand": "sales-and-marketing",
    "sales": "sales-and-marketing",
    "research-and-ai": "research-and-development",
    "r-and-d": "research-and-development",
    "advanced-manufacturing": "manufacturing-and-production",
    "manufacturing": "manufacturing-and-production",
    "production": "manufacturing-and-production",
    "customer-support": "customer-service",
    "customer-experience": "customer-service",
    "operations-and-back-office": "operations",
    "business-operations": "operations",
    "clinical": "clinical-and-care-delivery",
    "clinical-care": "clinical-and-care-delivery",
    "nursing": "clinical-and-care-delivery",
    "data-and-ai": "data-and-analytics",
    "analytics": "data-and-analytics",
}

VALUE_CHAIN = {"research", "design", "manufacture", "distribute", "operate", "service", "assure"}
DELIVERY_MODE = {"software", "physical-asset", "human-service", "marketplace", "content", "advisory"}

STOP = set("""a an the and or of for to in on with by from at as is are be been that this
their its our we you all more most other into over under new used using use provide provides
provided including include includes across both such than then them they he she his her
company companies business businesses customers clients customer client service services
solution solutions product products market markets global world leading leader innovative
innovation experience experiences people team teams work works working million billion
support supports supporting operate operates operating manage manages managing offer offers
offering deliver delivers delivering
""".split())

def _slug(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (t or "").lower().strip()).strip("-")

def canon_tag(t: str, corpus=None) -> str:
    """Canonicalize a capability tag.

    Suffix stripping is only applied when the stripped stem ALREADY EXISTS in the
    corpus (or the synonym table) -- otherwise "wealth-management" degrades to the
    meaningless "wealth". Merge only where a shorter variant genuinely competes.
    """
    t = _slug(t)
    if not t:
        return ""
    if t in SYNONYMS:
        return SYNONYMS[t]
    for suf in SUFFIXES:
        if t.endswith(suf) and len(t) > len(suf) + 4:
            cand = t[: -len(suf)]
            if cand in SYNONYMS:
                return SYNONYMS[cand]
            if corpus and cand in corpus:
                return cand
            break
    return t

def canon_family(f: str) -> str:
    f = re.sub(r"[^a-z0-9]+", "-", (f or "").lower().strip()).strip("-")
    return FAMILY_SYNONYMS.get(f, f)

def toks(text: str):
    return [w for w in re.findall(r"[a-z][a-z0-9\-]{2,}", (text or "").lower())
            if w not in STOP and len(w) > 2]


def coerce_vocabs(value_chain, delivery_mode):
    """Move values that belong on the other field; never invent subject matter.

    Extractors occasionally parked 'advisory' or 'content' on value_chain.
    If value_chain is empty after the move, default to 'service' — the least
    specific closed-vocab position that still describes an operating firm.
    """
    raw_vc = {str(v).lower() for v in (value_chain or []) if v}
    raw_dm = {str(v).lower() for v in (delivery_mode or []) if v}
    vc = sorted((raw_vc & VALUE_CHAIN) | (raw_dm & VALUE_CHAIN))
    dm = sorted((raw_dm & DELIVERY_MODE) | (raw_vc & DELIVERY_MODE))
    if not vc:
        vc = ["service"]
    return vc, dm

def main():
    seed = {r["slug"]: r for r in json.loads((ROOT / "seed" / "companies.json").read_text())}
    files = sorted(glob.glob(str(ROOT / "profiles" / "*.json")))

    # pass 1: synonym-only canonical forms, to learn which short stems really exist
    pass1 = collections.Counter()
    for f in files:
        d = json.load(open(f))
        for t in d.get("capability_tags", []) or []:
            s = _slug(t)
            pass1[SYNONYMS.get(s, s)] += 1
    corpus = {t for t, c in pass1.items() if c >= 1}

    out = []
    for f in files:
        d = json.load(open(f))
        slug = d.get("slug") or pathlib.Path(f).stem
        s = seed.get(slug, {})

        raw_tags = [t for t in d.get("capability_tags", []) if t]
        ctags = sorted({canon_tag(t, corpus) for t in raw_tags} - {""})

        fam = {}
        for fm in d.get("function_mix", []) or []:
            k = canon_family(fm.get("family", ""))
            if k:
                fam[k] = fam.get(k, 0) + float(fm.get("weight") or 0)
        tot = sum(fam.values()) or 1.0
        fam = {k: round(v / tot, 4) for k, v in sorted(fam.items(), key=lambda x: -x[1])}

        stmts = [a.get("statement", "") for a in d.get("activity_statements", []) or []]
        tag_tokens = collections.Counter(w for t in ctags for w in t.split("-") if w not in STOP and len(w) > 2)
        stmt_tokens = collections.Counter(w for s_ in stmts for w in toks(s_))
        vc, dm = coerce_vocabs(d.get("value_chain"), d.get("delivery_mode"))

        out.append({
            "slug": slug,
            "company": d.get("company") or s.get("company") or slug,
            "domain": d.get("domain") or s.get("domain", ""),
            "seed_indexes": s.get("seed_indexes", []),
            "index_count": s.get("index_count", 0),
            "index_industry_labels": s.get("index_industry_labels", []),
            "capability_tags": ctags,
            "capability_tags_raw": raw_tags,
            "function_mix": fam,
            "value_chain": vc,
            "delivery_mode": dm,
            "segments": d.get("segments", []) or [],
            "activity_statements": stmts,
            "n_statements": len(stmts),
            "name_reality_gap": (d.get("name_reality_gap") or "").strip(),
            "sources": d.get("sources", []) or [],
            "extraction_confidence": d.get("extraction_confidence"),
            "extraction_notes": d.get("extraction_notes", ""),
            "tag_tokens": dict(tag_tokens),
            "stmt_tokens": dict(stmt_tokens),
        })

    (ROOT / "out").mkdir(exist_ok=True)
    (ROOT / "out" / "normalized.json").write_text(json.dumps(out, indent=1), encoding="utf-8")

    all_tags = collections.Counter(t for r in out for t in r["capability_tags"])
    raw_n = len({t for r in out for t in r["capability_tags_raw"]})
    print(f"profiles normalized : {len(out)}")
    print(f"tags  raw -> canon  : {raw_n} -> {len(all_tags)}")
    print(f"canon tags shared by >=2 firms : {sum(1 for v in all_tags.values() if v >= 2)}")
    print(f"canon tags used once           : {sum(1 for v in all_tags.values() if v == 1)}")
    fams = collections.Counter(k for r in out for k in r["function_mix"])
    print(f"function families raw -> canon : {len({canon_family(k) for r in out for k in r['function_mix']})} canon, top:")
    for k, v in fams.most_common(12):
        print(f"   {v:3d}  {k}")
    print("\ntop canon tags:")
    for t, c in all_tags.most_common(20):
        print(f"   {c:3d}  {t}")

if __name__ == "__main__":
    main()
