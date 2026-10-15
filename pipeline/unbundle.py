#!/usr/bin/env python3
"""Explode a firm into line-of-work nodes when it has real segments.

Sane assumptions (also printed on the PoC page):
  - A segment counts only if it carries at least two capability tags.
  - A firm splits only if it has two or more such segments. One tagged
    division is not a conglomerate; leaving it as a firm avoids fake atoms.
  - Segment nodes keep their own tags. They do not inherit the parent's
    leftover tags — that re-smears the ticker.
  - Function mix / statements stay on the parent and are NOT used in the
    PoC similarity. Using them would pull every Amazon segment toward
    warehouses AND AWS at once, which is the bug being tested.
"""
import re

MIN_SEG_TAGS = 2
MIN_SEGS_TO_SPLIT = 2


def _slug(t: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (t or "").lower().strip()).strip("-")
    return s


def qualifying_segments(profile: dict) -> list:
    out = []
    for s in profile.get("segments") or []:
        tags = [t for t in (s.get("capability_tags") or []) if t]
        if len(tags) >= MIN_SEG_TAGS:
            out.append({
                "name": (s.get("name") or "").strip() or "unnamed",
                "weight": s.get("weight"),
                "capability_tags": tags,
            })
    return out


def canon_tags(raw, canon, corpus) -> list:
    return sorted({canon(t, corpus) for t in (raw or []) if t} - {""})


def explode_profile(profile: dict, canon, corpus=None) -> list:
    """Return 1 firm node, or N segment nodes. Never both."""
    slug = profile.get("slug") or ""
    company = profile.get("company") or slug
    segs = qualifying_segments(profile)
    if len(segs) < MIN_SEGS_TO_SPLIT:
        return [{
            "id": slug,
            "kind": "firm",
            "parent": slug,
            "parent_name": company,
            "name": company,
            "segment": None,
            "weight": 1.0,
            "capability_tags": canon_tags(profile.get("capability_tags"), canon, corpus),
        }]
    nodes = []
    seen = set()
    for s in segs:
        sid = _slug(s["name"]) or "seg"
        nid = f"{slug}::{sid}"
        if nid in seen:
            nid = f"{nid}-{len(seen)}"
        seen.add(nid)
        nodes.append({
            "id": nid,
            "kind": "segment",
            "parent": slug,
            "parent_name": company,
            "name": f"{company} · {s['name']}",
            "segment": s["name"],
            "weight": s["weight"],
            "capability_tags": canon_tags(s["capability_tags"], canon, corpus),
        })
    return nodes


def firm_node(profile: dict, canon, corpus=None) -> dict:
    slug = profile.get("slug") or ""
    company = profile.get("company") or slug
    return {
        "id": slug,
        "kind": "firm",
        "parent": slug,
        "parent_name": company,
        "name": company,
        "segment": None,
        "weight": 1.0,
        "capability_tags": canon_tags(profile.get("capability_tags"), canon, corpus),
    }


def token_counts(tags) -> dict:
    from collections import Counter
    return dict(Counter(w for t in tags for w in t.split("-") if len(w) > 2))
