#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kursk EIS: Bothub filter + full detail parse."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from procurement.bothub import classify_rows
from procurement.config import bothub_config, load_dotenv
from procurement.enrich import eis_to_rows
from procurement.kursk_discover import discover_kursk_eis, save_kursk_discovery
from procurement.schema import REJECTED_COLUMNS, TARGET_COLUMNS

KURSK_OBJECTS = ["Курская АЭС", "Курская АЭС-2"]


def load_kursk_items(discovery_path: Path):
    from run_kursk_parse import load_kursk
    return load_kursk(discovery_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--discovery", default="output/kursk_discovery_cache.json")
    ap.add_argument("--out", default="output/kursk_eis_parsed_v3.xlsx")
    ap.add_argument("--kept-regs", default="output/kursk_kept_regs.json")
    ap.add_argument("--rediscover", action="store_true")
    ap.add_argument("--skip-discover", action="store_true")
    ap.add_argument("--skip-bothub", action="store_true")
    ap.add_argument("--skip-parse", action="store_true")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    load_dotenv()
    discovery = Path(args.discovery)
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)

    if args.rediscover or not discovery.is_file():
        print("=== Phase 1: Discovery 2020-2026 ===")
        by_reg, stats = discover_kursk_eis()
        save_kursk_discovery(by_reg, stats, discovery)
        print("Discovery saved:", stats["total_notices"], "notices")
    elif args.skip_discover:
        print("=== Phase 1: skipped (using cache) ===")
    else:
        print("=== Phase 1: using", discovery, "===")

    disc = json.loads(discovery.read_text(encoding="utf-8"))
    by_reg = disc.get("eis_by_reg") or disc
    items = load_kursk_items(discovery)
    header_rows = eis_to_rows({x["reg"]: x["item"] for x in items})
    print("Header rows for filter:", len(header_rows))

    kept_regs_path = Path(args.kept_regs)
    if args.skip_bothub and kept_regs_path.is_file():
        kept_regs = json.loads(kept_regs_path.read_text(encoding="utf-8"))
        print("=== Phase 2: Bothub skipped, loaded", len(kept_regs), "kept regs ===")
    elif args.skip_bothub:
        kept_regs = [x["reg"] for x in items]
        kept_regs_path.write_text(json.dumps(kept_regs, ensure_ascii=False), encoding="utf-8")
    else:
        print("=== Phase 2: Bothub filter ===")
        cfg = bothub_config()
        print("Bothub:", cfg.get("model"), ("ok" if cfg.get("api_key") else "heuristic fallback"))
        kept, rejected = classify_rows(header_rows, KURSK_OBJECTS)
        kept_regs = [r["Notice number"] for r in kept if r.get("Notice number")]
        kept_regs_path.write_text(json.dumps(kept_regs, ensure_ascii=False), encoding="utf-8")
        print("Bothub: kept", len(kept), "rejected", len(rejected))
        kept_df = pd.DataFrame(kept)
        rej_df = pd.DataFrame(rejected)
        for c in TARGET_COLUMNS:
            if c not in kept_df.columns:
                kept_df[c] = ""
            if c not in rej_df.columns:
                rej_df[c] = ""
        if "_filter_reason" not in rej_df.columns:
            rej_df["_filter_reason"] = ""
        kept_df[TARGET_COLUMNS].to_excel(out_dir / "kursk_bothub_kept.xlsx", index=False)
        rej_df[REJECTED_COLUMNS].to_excel(out_dir / "kursk_bothub_rejected.xlsx", index=False)

    if args.skip_parse:
        print("Parse skipped.")
        return 0

    print("=== Phase 3: Full detail parse on", len(kept_regs), "notices ===")
    cmd = [
        sys.executable,
        "run_kursk_parse.py",
        "--discovery", str(discovery),
        "--out", args.out,
        "--kept-regs", str(kept_regs_path),
        "--checkpoint-every", "25",
    ]
    if args.resume:
        cmd.append("--resume")
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
