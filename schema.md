# Activity Profile Schema (v1) — the contract every record must satisfy

This is the ONLY structure allowed into the map. One JSON file per company at
`/agent/workspace/orgmap/profiles/<slug>.json`.

## HARD PRIVACY RULE — firm-level only

A record is INVALID and will be rejected by the scrub pass if it contains:
- any person's name (executives, founders, employees, review authors, journalists)
- any job title attached to a person ("their CTO said...")
- any email, phone number, social handle, or personal URL
- any per-person compensation, review quote attributed to an individual, or headcount broken to a person

Job FAMILIES in aggregate are allowed and wanted ("staffs actuarial, claims adjudication,
and catastrophe modeling"). A family is a kind of work, never a person.

## Fields

```jsonc
{
  "slug": "jpmorgan-chase",              // lowercase, hyphenated, stable id
  "company": "JPMorganChase",            // canonical display name
  "domain": "jpmorganchase.com",

  // 1. ACTIVITY STATEMENTS — the core of the map. 5-12 per company.
  // Form: verb + object + for-whom. Concrete, not marketing language.
  // GOOD: "operates a domestic parcel sortation and line-haul network"
  // GOOD: "underwrites commercial property and casualty risk for mid-market firms"
  // BAD:  "delivers world-class customer experiences"  (no activity)
  // BAD:  "is a leader in innovation"                  (no activity)
  "activity_statements": [
    {
      "statement": "operates retail bank branches and consumer deposit services",
      "source_url": "https://...",
      "confidence": 0.9                  // 0-1, your read of how clearly the source supports it
    }
  ],

  // 2. CAPABILITY TAGS — normalized slugs, emergent vocabulary (NOT NAICS/SIC).
  // Lowercase, hyphenated, verb-led where possible. 6-15 per company.
  // Reuse tags you'd expect other firms to share — that shared-ness IS the graph edge.
  // e.g. "consumer-lending", "fraud-detection", "regulatory-compliance-ops",
  //      "physical-branch-network", "core-transaction-processing", "24x7-noc",
  //      "cold-chain-logistics", "clinical-care-delivery", "semiconductor-fabrication",
  //      "ad-inventory-marketplace", "field-service-technicians", "actuarial-modeling"
  "capability_tags": ["consumer-lending", "fraud-detection", "..."],

  // 3. FUNCTION MIX — job FAMILIES the firm staffs at scale. 4-10.
  // weight: rough share of the firm's staffing attention, 0-1, need not sum exactly.
  "function_mix": [
    { "family": "software-engineering", "weight": 0.25 },
    { "family": "risk-and-compliance",  "weight": 0.2 }
  ],

  // 4. VALUE CHAIN POSITION — controlled vocabulary, pick 1-3 that genuinely apply:
  // "research" | "design" | "manufacture" | "distribute" | "operate" | "service" | "assure"
  //  assure = regulate/audit/insure/verify
  "value_chain": ["operate", "service", "assure"],

  // 5. DELIVERY MODE — controlled vocabulary, pick 1-3:
  // "software" | "physical-asset" | "human-service" | "marketplace" | "content" | "advisory"
  "delivery_mode": ["software", "human-service"],

  // 6. SEGMENTS — for multi-line firms. If the firm genuinely does several distinct
  // things, split them. This is what stops a conglomerate landing in one wrong place.
  // Omit or leave [] for single-line firms.
  "segments": [
    { "name": "Consumer & Community Banking", "weight": 0.45,
      "capability_tags": ["consumer-lending", "physical-branch-network"] }
  ],

  // 7. THE SELF-DESCRIPTION vs REALITY GAP — free text, 1-2 sentences.
  // What would someone wrongly assume from the company's NAME or its index industry
  // label, versus what the activity evidence actually shows? This feeds the
  // "hidden employer" wedge. Write "none" if the name is an honest description.
  "name_reality_gap": "Reads as a retailer; activity evidence is dominated by a national logistics network and a retail-media ad marketplace.",

  // 8. PROVENANCE — every source you actually read.
  "sources": [
    { "url": "https://...", "kind": "about-page", "retrieved_at": "2026-08-19" }
  ],
  // kind: "about-page" | "what-we-do" | "product-page" | "careers-page" |
  //       "10k-item1" | "segment-reporting" | "engineering-blog" | "newsroom" | "other"

  "extraction_notes": "10-K segment data unavailable (private company); profile built from about + careers pages.",
  "extraction_confidence": 0.8            // overall 0-1
}
```

## Rules of thumb

- **Evidence over vibes.** Every activity statement must trace to a source you read.
  If a page is pure marketing with no activity content, say so in `extraction_notes`
  and lower `extraction_confidence` rather than inventing plausible activities.
- **Don't smooth toward the industry stereotype.** If a bank's careers page is 60%
  software roles, the function mix says so. The whole point of this map is to catch
  what the industry label hides.
- **Prefer the firm's own words** (about, 10-K Item 1, careers) over press coverage.
- **Multi-line firms**: use `segments`. A firm doing 5 unrelated things with one blended
  profile is a failed record.
- Partial records are acceptable and useful; fabricated records poison the graph.
