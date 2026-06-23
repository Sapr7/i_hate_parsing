#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Enrich existing final_procurements.xlsx after Bothub (kept rows only)."""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from procurement.enrich_cards import enrich_kept_rows
from procurement.schema import TARGET_COLUMNS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", default="output/final_procurements.xlsx")
    ap.add_argument("--out", default="output/final_procurements_enriched.xlsx")
    ap.add_argument("--overlaps", default="output/source_overlaps.json")
    ap.add_argument("--no-headless", action="store_true")
    args = ap.parse_args()

    df = pd.read_excel(args.in_path)
    rows = df.to_dict("records")
    print("Input rows:", len(rows))
    overlaps: list = []
    enriched = enrich_kept_rows(rows, headless=not args.no_headless, overlaps_out=overlaps)
    out_df = pd.DataFrame(enriched)
    for c in TARGET_COLUMNS:
        if c not in out_df.columns:
            out_df[c] = ""
    out_df = out_df[TARGET_COLUMNS]
    out_path = Path(args.out)
    out_df.to_excel(out_path, index=False)

    overlap_path = Path(args.overlaps)
    overlap_path.write_text(json.dumps(overlaps, ensure_ascii=False, indent=2), encoding="utf-8")
    if overlaps:
        pd.DataFrame(overlaps).to_excel(overlap_path.with_suffix(".xlsx"), index=False)

    both_urls = (
        out_df["EIS URL"].astype(str).str.strip().isin(("", "nan")).eq(False)
        & out_df["Rosatom URL"].astype(str).str.strip().isin(("", "nan")).eq(False)
    ).sum()
    fill = {
        c: int((out_df[c].notna() & (out_df[c].astype(str).str.strip() != "")).sum())
        for c in TARGET_COLUMNS
    }
    summary = {
        "rows_in": len(rows),
        "rows_out": len(out_df),
        "overlaps_merged": len(overlaps),
        "rows_with_both_urls": int(both_urls),
        "fill_rates": fill,
    }
    out_path.with_suffix(".summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Overlaps:", len(overlaps), "->", overlap_path)
    print("Rows with EIS+Rosatom URL:", both_urls)
    print("DONE:", out_path, len(out_df), "rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
