#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified loose scan: EIS (objects + customer INN) + Rosatom list discovery.
Applies heuristic reasoning filter (Bothub hook placeholder).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

from procurement.eis_client import (
    object_search_queries,
    scan_customer_inn,
    scan_query_loose,
)
from procurement.matching import loose_match, strict_match
from procurement.objects import load_customer_inns, load_objects
from procurement.reasoning_filter import apply_filter
from procurement.rosatom_discover import discover_rosatom_ids


def records_to_rows(by_reg: dict) -> list:
    rows = []
    for reg, item in by_reg.items():
        row = {
            "id": reg,
            "source": item.get("source", "eis"),
            "title": item.get("title", ""),
            "customer": item.get("customer", ""),
            "url": item.get("url", ""),
            "matched_objects": "; ".join(sorted(item.get("matched_objects", []))),
            "queries": "; ".join(sorted(item.get("queries", []))),
            "customer_inn": item.get("customer_inn", ""),
        }
        apply_filter(row)
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default="2 (3).xlsx")
    ap.add_argument("--out-dir", default="output")
    ap.add_argument("--skip-rosatom", action="store_true")
    ap.add_argument("--skip-customer-inn", action="store_true")
    ap.add_argument("--no-headless", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    objects = load_objects(args.xlsx)
    print(f"Objects to scan: {len(objects)}")

    by_reg: dict = {}
    stats = []

    # --- EIS by object keywords (loose) ---
    t0 = time.time()
    for i, name in enumerate(objects, 1):
        for q in object_search_queries(name):
            try:
                found, total_txt = scan_query_loose(q, name, by_reg)
                stats.append(("eis_object", name, q, total_txt, found))
            except Exception as err:
                stats.append(("eis_object", name, q, f"ERROR:{err}", 0))
            time.sleep(0.25)
        if i % 10 == 0:
            print(f"  EIS objects {i}/{len(objects)}, unique={len(by_reg)}")
    eis_object_count = len(by_reg)
    print(f"EIS object scan done: {eis_object_count} unique ({time.time()-t0:.0f}s)")

    # --- EIS by customer INN (broader pool) ---
    inn_new = 0
    if not args.skip_customer_inn:
        t1 = time.time()
        for org, inn in load_customer_inns(args.xlsx):
            before = len(by_reg)
            try:
                found, total_txt = scan_customer_inn(inn, org, objects, by_reg)
                added = len(by_reg) - before
                inn_new += added
                stats.append(("eis_inn", org, inn, total_txt, found))
            except Exception as err:
                stats.append(("eis_inn", org, inn, f"ERROR:{err}", 0))
            time.sleep(0.3)
        print(f"EIS customer INN scan: +{inn_new} new, total={len(by_reg)} ({time.time()-t1:.0f}s)")

    # --- Rosatom list discovery ---
    rosatom_ids: dict = {}
    if not args.skip_rosatom:
        print("Rosatom list discovery (Selenium)...")
        try:
            rosatom_ids = discover_rosatom_ids(headless=not args.no_headless)
            print(f"Rosatom visible IDs discovered: {len(rosatom_ids)}")
        except Exception as err:
            print(f"Rosatom discovery failed: {err}")

    rows = records_to_rows(by_reg)
    df = pd.DataFrame(rows)

    # Compare strict vs loose on EIS object-sourced subset
    strict_hits = 0
    for _, r in df.iterrows():
        objs = [x.strip() for x in str(r["matched_objects"]).split(";") if x.strip()]
        if objs and strict_match(r["title"], objs[0]):
            strict_hits += 1

    verdict_counts = df["ai_verdict"].value_counts().to_dict() if len(df) else {}
    keep_df = df[df["ai_verdict"].isin(["keep", "review"])] if len(df) else df

    # Export
    df.to_excel(out_dir / "scan_loose_all.xlsx", index=False)
    keep_df.to_excel(out_dir / "scan_reasoning_kept.xlsx", index=False)
    reject_df = df[df["ai_verdict"] == "reject"] if len(df) else df
    reject_df.to_excel(out_dir / "scan_reasoning_rejected.xlsx", index=False)

    summary = {
        "objects_scanned": len(objects),
        "eis_unique_loose": len(by_reg),
        "eis_from_object_search": eis_object_count,
        "eis_added_via_customer_inn": inn_new,
        "strict_match_subset": strict_hits,
        "reasoning_keep": verdict_counts.get("keep", 0),
        "reasoning_review": verdict_counts.get("review", 0),
        "reasoning_reject": verdict_counts.get("reject", 0),
        "reasoning_kept_total": len(keep_df),
        "rosatom_ids_discovered": len(rosatom_ids),
        "check_32312016595_in_loose": "32312016595" in by_reg,
        "check_32312016595_in_kept": bool(
            len(df) and len(df[df["id"].astype(str) == "32312016595"]) 
            and df[df["id"].astype(str) == "32312016595"]["ai_verdict"].iloc[0] in ("keep", "review")
        ),
    }
    (out_dir / "scan_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n=== SUMMARY ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"\nSaved: {out_dir}/scan_loose_all.xlsx")
    print(f"       {out_dir}/scan_reasoning_kept.xlsx")
    return 0


if __name__ == "__main__":
    sys.exit(main())
