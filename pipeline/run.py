#!/usr/bin/env python3
"""Run the activity-map pipeline end to end.

Stages
------
  1. dedupe     seed/seed_raw.csv          -> seed/companies.json
  2. validate   profiles/*.json            -> out/validate_report.json
  3. normalize  profiles + seed            -> out/normalized.json
  4. build      normalized.json            -> out/map.json, out/scrub_report.json
  5. expand     expansion/cluster_*.json   -> fold off-index firms into map.json
  6. page       map.json + template        -> out/orgmap.html

Extraction of new profiles is deliberately NOT in this runner: it is an
evidence-gathering step that a person or agent performs against schema.md.
This pipeline only accepts profiles that already exist on disk.
"""
import argparse, json, subprocess, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = sys.executable

STAGES = [
    ("dedupe", "pipeline/dedupe_seed.py"),
    ("validate", "pipeline/validate.py"),
    ("normalize", "pipeline/normalize.py"),
    ("build", "pipeline/build_map.py"),
    ("expand", "pipeline/merge_expansion.py"),
    ("page", "pipeline/gen_page.py"),
]


def run_stage(name: str, script: str) -> None:
    print(f"\n{'=' * 64}\n==> {name}: {script}\n{'=' * 64}")
    r = subprocess.run([PY, str(ROOT / script)], cwd=ROOT)
    if r.returncode != 0:
        sys.exit(r.returncode)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="start", choices=[s[0] for s in STAGES],
                    help="resume from this stage (inclusive)")
    ap.add_argument("--only", choices=[s[0] for s in STAGES],
                    help="run a single stage")
    ap.add_argument("--fail-on-scrub", action="store_true",
                    help="exit non-zero if the privacy scrub flagged anything")
    args = ap.parse_args(argv)

    stages = STAGES
    if args.only:
        stages = [s for s in STAGES if s[0] == args.only]
    elif args.start:
        names = [s[0] for s in STAGES]
        stages = STAGES[names.index(args.start):]

    for name, script in stages:
        run_stage(name, script)

    if args.fail_on_scrub:
        report = ROOT / "out" / "scrub_report.json"
        if report.exists():
            viol = json.loads(report.read_text(encoding="utf-8"))
            if viol:
                print(f"\nscrub FAILED — {len(viol)} violation(s)")
                return 1

    print("\npipeline OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
