#!/usr/bin/env python3
"""Firm-level privacy gate. Person-level content is a hard reject.

A record is invalid if it contains a person's name, a job title attached to a
person, an email, a phone number, or any other individual identifier. Job
FAMILIES in aggregate ("staffs actuarial and claims adjudication") are allowed.
"""
import re

EMAIL = re.compile(r"[\w.\-+]+@[\w\-]+\.[a-z]{2,}", re.I)
PHONE = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)")
PERSONISH = re.compile(
    r"\b(?:CEO|CFO|CTO|COO|CIO|CHRO|chief executive|chief financial|chief technology|"
    r"founder|co-founder|chairman|chairwoman|president|spokesperson|our recruiter|"
    r"hiring manager)\b[^.]{0,40}\b[A-Z][a-z]+\s+[A-Z][a-z]+\b"
    r"|\b[A-Z][a-z]+\s+[A-Z][a-z]+\b(?=[^.]{0,25}\b(?:said|says|told|joined|leads|founded)\b)"
)

HARD_KINDS = ("email", "phone", "person")


def blob_from_record(rec: dict) -> str:
    """Flatten the free-text fields a person-name could hide in."""
    stmts = rec.get("activity_statements") or []
    parts = []
    for s in stmts:
        if isinstance(s, dict):
            parts.append(s.get("statement") or "")
        else:
            parts.append(str(s or ""))
    parts.append(rec.get("name_reality_gap") or "")
    parts.append(rec.get("extraction_notes") or "")
    return " ".join(parts)


def source_urls(rec: dict) -> list:
    urls = []
    for s in rec.get("sources") or []:
        if isinstance(s, dict) and (s.get("url") or "").strip():
            urls.append(s["url"].strip())
    if rec.get("source_url"):
        urls.append(str(rec["source_url"]).strip())
    return urls


def find_violations(rec: dict) -> list:
    """Return a list of {slug, kind, match} dicts. Empty means the record is clean."""
    slug = rec.get("slug") or rec.get("company") or ""
    viol = []
    blob = blob_from_record(rec)
    for label, rx in (("email", EMAIL), ("phone", PHONE), ("person", PERSONISH)):
        m = rx.search(blob)
        if m:
            viol.append({"slug": slug, "kind": label, "match": m.group(0)[:80]})
    if not source_urls(rec):
        viol.append({"slug": slug, "kind": "no_provenance", "match": ""})
    return viol


def scrub(recs) -> list:
    out = []
    for r in recs:
        out.extend(find_violations(r))
    return out
