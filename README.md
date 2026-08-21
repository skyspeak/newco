# Activity Map

An organizational map of US employers built on **what firms actually do**, not the industry label a ranking slapped on them.

Best-places-to-work indexes describe Amazon as "Software Development" and Hilton as hospitality. Activity evidence shows a fulfillment network plus a cloud utility in one case, and a room-night machine in the other. This repo extracts firm-level activity profiles, clusters them by work rather than NAICS, and surfaces the gaps: mislabeled peers, hidden employers, and off-index firms doing the same work.

The interactive map is generated at `out/orgmap.html`.

## Pipeline

```
seed/seed_raw.csv          1. dedupe      seed/companies.json
profiles/*.json            2. validate    schema + privacy gate
profiles + seed            3. normalize   canonical tags / families / tokens
out/normalized.json        4. build       similarity, clusters, wedges
expansion/cluster_*.json   5. expand      off-index existence proof
out/map.json + template    6. page        out/orgmap.html
```

Extraction of new profiles is **not** in the runner. A person or agent reads sources against `schema.md` and writes one JSON file per firm. The pipeline only accepts profiles that already exist on disk — fabricated records poison the graph.

```bash
python3 -m pip install -r requirements.txt
make test
make map          # or: python3 pipeline/run.py --fail-on-scrub
```

Resume from a later stage with `python3 pipeline/run.py --from normalize`. Open `out/orgmap.html` in a browser.

## Contract

Every profile must satisfy `schema.md`. Hard rules:

- Firm-level only. No person names, titles attached to people, emails, phones.
- Every activity statement traces to a source URL you actually read.
- Capability tags are an emergent vocabulary, not NAICS. Shared tags *are* the graph edges.
- `value_chain` and `delivery_mode` are closed vocabularies.
- Partial records are allowed. Invented records are not.

`pipeline/validate.py` enforces the contract. CI fails the build on hard violations or a privacy-scrub hit.

## Layout

```
seed/          composite best-places indexes (CSV → one row per company)
profiles/      147 extracted activity profiles (the map's input)
expansion/     off-index firms per activity cluster (existence proof, search-capped)
pipeline/      stages + page template
out/           normalized.json, map.json, orgmap.html
tests/         privacy, sector voting, tag canonicalization, schema
schema.md      the only structure allowed into the map
```

## What the map measures

Sectors are assigned two ways and **never used to build the clusters**:

- `sector_claimed` — from the index's own industry label
- `sector_actual` — voted from the firm's extracted capability tags

Disagreement is a finding (the incumbent labelling error rate). Clustering is average-linkage on a blend of canonical tags, tag tokens, statement tokens, function mix, and delivery mode. Cluster names are assigned after the fact from tag lift.

## License of the data

Seed rows come from publicly published 2026 employer rankings. Profiles were extracted from each firm's own about / 10-K / careers pages. Treat this as a research snapshot, not a commercial directory.
