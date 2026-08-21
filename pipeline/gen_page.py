#!/usr/bin/env python3
"""Stage 10: render out/map.json into a self-contained interactive webpage."""
import json, pathlib, html

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"

# Curated names keyed by a signature tag, not by cluster id.
# Integer ids reshuffle whenever the seed or synonym table moves.
NAME_BY_SIGNAL = {
    "inventory-management": "Store networks & physical distribution",
    "grocery-retail-operations": "Store networks & physical distribution",
    "store-network-management": "Store networks & physical distribution",
    "fraud-detection": "Money movement, risk & claims",
    "digital-banking": "Money movement, risk & claims",
    "claims-adjudication": "Money movement, risk & claims",
    "core-transaction-processing": "Money movement, risk & claims",
    "semiconductor-design": "Platforms, silicon & content systems",
    "semiconductor-fabrication": "Platforms, silicon & content systems",
    "saas-productivity-suite": "Platforms, silicon & content systems",
    "pharmaceutical-drug-development": "Molecules, barrels & regulated pipelines",
    "upstream-oil-and-gas": "Molecules, barrels & regulated pipelines",
    "revenue-management-and-pricing": "Perishable capacity & guest throughput",
    "quick-service-restaurant-operations": "Perishable capacity & guest throughput",
    "hotel-management-contracts": "Perishable capacity & guest throughput",
    "scheduled-passenger-air-service": "Perishable capacity & guest throughput",
    "electric-vehicle-development": "Engineered hardware & defense systems",
    "vehicle-manufacturing": "Engineered hardware & defense systems",
    "electronic-warfare": "Engineered hardware & defense systems",
    "management-consulting": "Advisory, assurance & systems integration",
    "audit-and-assurance": "Advisory, assurance & systems integration",
    "value-based-care": "Care delivery & population risk",
    "primary-care-network": "Care delivery & population risk",
    "clinical-care-delivery": "Care delivery & population risk",
    "program-management": "Built environment & infrastructure programs",
    "construction-management": "Built environment & infrastructure programs",
    "infrastructure-engineering": "Built environment & infrastructure programs",
    "theme-park-operations": "Destination entertainment & parks",
    "field-service-merchandising": "Field execution & administered programs",
    "competitive-pricing-intelligence": "Field execution & administered programs",
}


def cluster_name(c):
    for t in c.get("signature_tags") or []:
        if t in NAME_BY_SIGNAL:
            return NAME_BY_SIGNAL[t]
    tags = c.get("signature_tags") or []
    if tags:
        return " · ".join(t.replace("-", " ") for t in tags[:3])
    return f"Cluster {c['id']}"

def main():
    m = json.loads((OUT / "map.json").read_text())
    st = m["stats"]

    companies = [{
        "s": c["slug"], "n": c["company"], "d": c.get("domain", ""),
        "c": c["cluster"], "sec": c["sector"], "secc": c.get("sector_claimed", ""),
        "mm": bool(c.get("sector_mismatch")),
        "lab": c.get("index_labels", [])[:2],
        "idx": c.get("seed_indexes", []),
        "t": c.get("tags", [])[:14],
        "f": list(c.get("families", {}).items())[:6],
        "vc": c.get("value_chain", []), "dm": c.get("delivery_mode", []),
        "st": c.get("statements", [])[:7],
        "g": c.get("name_reality_gap", ""),
        "seg": c.get("segments", [])[:5],
        "cf": c.get("confidence"), "src": c.get("n_sources", 0),
        "nb": [{"n": x["company"], "s": x["slug"], "v": x["sim"]} for x in c.get("neighbors", [])[:6]],
    } for c in m["companies"]]

    payload = {
        "stats": st,
        "clusters": [{
            "id": c["id"], "name": cluster_name(c),
            "size": c["size"], "sig": c["signature_tags"][:8],
            "fams": c["top_families"][:5], "vc": c["value_chain"], "dm": c["delivery_mode"],
            "labels": c["index_labels"][:8], "nlabels": c["distinct_index_labels"],
            "sectors": list(c.get("sector_mix", {}).items())[:5],
            "sim": c["mean_internal_sim"], "members": c["members"],
        } for c in m["clusters"]],
        "companies": companies,
        "op_twins": m.get("op_twins", [])[:26],
        "hidden": [h for h in m.get("hidden_employers", []) if h.get("name_reality_gap")][:34],
        "mismatch": m.get("sector_mismatches", [])[:50],
        "expansion": m.get("expansion", []),
        "coverage": m.get("expansion_coverage", []),
        "ladders": m.get("ladders", [])[:6],
        "portable": m.get("portable_capabilities", [])[:24],
        "scarce": m.get("concentration_scarce", [])[:24],
        "common": m.get("concentration_common", [])[:20],
    }
    data = json.dumps(payload, separators=(",", ":"))

    tpl = (ROOT / "pipeline" / "page_template.html").read_text()
    out = tpl.replace("/*__DATA__*/", data)
    (OUT / "orgmap.html").write_text(out, encoding="utf-8")
    print(f"wrote {OUT/'orgmap.html'} ({round(len(out)/1024)} KB)")

if __name__ == "__main__":
    main()
