#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, pathlib, sys

# Support the documented direct-script invocation from the clinicaltrials root.
_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_ESTATE_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ESTATE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ESTATE_ROOT))
from canonical.clinicaltrials.extractor import ExtractionConfig, MassExtractor
from canonical.clinicaltrials.storage import save_ddls
from canonical.config import DEFAULT_OUTPUT, DEFAULT_RATE_PER_SEC, PRESETS
from frontier_core.gate import require_frontier_preflight

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    p.add_argument("--page-size", type=int, default=1000)
    p.add_argument("--query")
    p.add_argument("--preset", choices=PRESETS.keys())
    p.add_argument("--max", type=int, dest="max_studies")
    p.add_argument("--rate", type=float, default=DEFAULT_RATE_PER_SEC)
    p.add_argument("--bulk", action="store_true", help="Use official all-study JSON ZIP; only appropriate for an unfiltered full snapshot")
    p.add_argument("--no-resume", action="store_true")
    p.add_argument("--nct")
    p.add_argument("--save-ddl", action="store_true")
    p.add_argument("--network", action="store_true", help="Explicitly authorize network access. Required for any source fetch/extraction.")
    p.add_argument("--preflight", type=pathlib.Path, help="PASS FRONTIER_PREFLIGHT.json for the exact active code")
    args = p.parse_args()
    if args.save_ddl: save_ddls(args.output / "ddl")
    fetch_selector = bool(args.nct or args.bulk or args.query or args.preset)
    if args.save_ddl and not fetch_selector:
        print(json.dumps({"status":"completed","certification_status":"PASS","network_extraction_performed":False,"ddl_dir":str(args.output / "ddl")}, indent=2)); return
    network_requested = bool(fetch_selector or not args.save_ddl)
    if network_requested and not args.network:
        p.error("network extraction is locked; pass --network only after frontier preflight PASS")
    if network_requested:
        if not args.preflight: p.error("--preflight is required for network extraction")
        require_frontier_preflight(args.preflight, _ESTATE_ROOT)
    if args.nct and (args.query or args.preset or args.bulk):
        p.error("--nct cannot be combined with --query, --preset, or --bulk")
    query = (
        f"AREA[NCTId]{args.nct.upper()}" if args.nct
        else (PRESETS.get(args.preset) if args.preset else args.query)
    )
    if args.bulk and query:
        p.error("--bulk is only valid for an unfiltered full snapshot")
    effective_max = 1 if args.nct and args.max_studies is None else args.max_studies
    result = MassExtractor(ExtractionConfig(args.output, args.page_size, query, None, effective_max, args.rate, not args.no_resume, args.bulk)).run()
    print(json.dumps(result, indent=2))
if __name__ == "__main__": main()
