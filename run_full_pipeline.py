#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, json, sys, time
from pathlib import Path
import pandas as pd
from procurement.bothub import classify_rows
from procurement.config import bothub_config, load_dotenv
from procurement.discover import DiscoveryResult, discover_all, print_discovery_banner
from procurement.enrich_cards import enrich_kept_rows
from procurement.enrich import eis_to_rows, normalize_df_columns, rosatom_list_to_rows, rosatom_lists_to_rows, rosatom_to_rows
from procurement.rosatom import parse_procurements_batch
from procurement.rosatom_discover import rosatom_number_to_id
from procurement.schema import REJECTED_COLUMNS, TARGET_COLUMNS

def load_rosatom_keyword_rows(out_dir: Path, json_path: str, xlsx_path: str):
    xlsx = Path(xlsx_path)
    if xlsx.exists():
        df = pd.read_excel(xlsx)
        return df.to_dict("records")
    progress = out_dir / "rosatom_keyword_progress.json"
    if progress.exists():
        data = json.loads(progress.read_text(encoding="utf-8"))
        by_id = data.get("by_id") or {}
        if by_id:
            print("  loaded", len(by_id), "rows from", progress)
            return list(by_id.values())
    js = Path(json_path)
    if js.exists():
        data = json.loads(js.read_text(encoding="utf-8"))
        sample = data.get("sample") or []
        total = (data.get("stats") or {}).get("total", 0)
        if total and len(sample) < total:
            print("  keyword scan json has sample only;", total, "total   use", xlsx_path)
        return sample
    return []

def load_rosatom_full_rows(out_dir, json_path, xlsx_path):
    xlsx = Path(xlsx_path)
    if xlsx.exists():
        return pd.read_excel(xlsx).to_dict("records")
    js = Path(json_path)
    if js.exists():
        data = json.loads(js.read_text(encoding="utf-8"))
        by_id = data.get("by_id") or {}
        if by_id:
            print("  loaded", len(by_id), "rows from", js)
            return list(by_id.values())
    return []


def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default="2 (3).xlsx")
    ap.add_argument("--out-dir", default="output")
    ap.add_argument("--discovery-cache", default="output/discovery_cache.json")
    ap.add_argument("--skip-discovery", action="store_true")
    ap.add_argument("--discovery-only", action="store_true")
    ap.add_argument("--skip-customer-inn", action="store_true")
    ap.add_argument("--skip-rosatom-detail", action="store_true")
    ap.add_argument("--skip-bothub", action="store_true")
    ap.add_argument("--skip-enrich", action="store_true")
    ap.add_argument("--rosatom-pages", type=int, default=20)
    ap.add_argument("--max-eis", type=int, default=0)
    ap.add_argument("--max-rosatom", type=int, default=0)
    ap.add_argument("--rosatom-keyword-json", default="output/rosatom_keyword_scan.json")
    ap.add_argument("--rosatom-keyword-xlsx", default="output/rosatom_keyword_hits.xlsx")
    ap.add_argument("--rosatom-full-json", default="output/rosatom_full_aes.json")
    ap.add_argument("--rosatom-full-xlsx", default="output/rosatom_full_hits.xlsx")
    ap.add_argument("--no-headless", action="store_true")
    args = ap.parse_args()
    out_dir = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    cache_path = Path(args.discovery_cache)
    cfg = bothub_config()
    print("Bothub:", cfg["model"], "(ok)" if cfg["api_key"] else "(heuristic fallback)")
    if args.skip_discovery and cache_path.exists():
        discovery = DiscoveryResult.load(cache_path)
        print("Loaded cache:", cache_path)
        for k,v in discovery.stats.items(): print(" ", k, ":", v)
    else:
        discovery = discover_all(args.xlsx, skip_customer_inn=args.skip_customer_inn, rosatom_list_pages=args.rosatom_pages, headless=not args.no_headless, max_eis=args.max_eis, max_rosatom=args.max_rosatom)
        discovery.save(cache_path)
        print("Cache saved:", cache_path)
    if args.discovery_only: return 0
    print_discovery_banner(discovery)
    all_rows = []
    print("[Stage 2a] EIS rows...")
    eis_rows = eis_to_rows(discovery.eis_by_reg)
    print("  EIS rows:", len(eis_rows))
    all_rows.extend(eis_rows)
    rosatom_row_count = 0
    fab_pos = 0
    if not args.skip_rosatom_detail and discovery.rosatom_aes_filtered:
        urls = [r["url"] for r in discovery.rosatom_aes_filtered.values()]
        print("[Stage 2b] Rosatom cards:", len(urls), "+ Fabrikant...")
        t0 = time.time()
        headers = parse_procurements_batch(urls, headless=not args.no_headless, wait_sec=5)
        for header in headers:
            if header.get("error"): continue
            rid = rosatom_number_to_id(header.get("rosatom_number",""))
            if not rid: rid = header.get("source_url","").split("/")[-1].split("?")[0]
            lr = discovery.rosatom_aes_filtered.get(rid, {})
            matched = lr.get("matched_objects") or []
            if not matched and lr.get("matched_object"):
                matched = [lr["matched_object"]]
            rows = rosatom_to_rows(header, matched)
            fab_pos += sum(1 for r in rows if r.get("Quantity"))
            all_rows.extend(rows)
            rosatom_row_count += len(rows)
        print("  Rosatom card rows:", rosatom_row_count, "in", int(time.time()-t0), "sec")
        print("  Fabrikant positions:", fab_pos)
    else:
        keyword_items = load_rosatom_keyword_rows(out_dir, args.rosatom_keyword_json, args.rosatom_keyword_xlsx)
        full_items = load_rosatom_full_rows(out_dir, args.rosatom_full_json, args.rosatom_full_xlsx)
        if full_items:
            print("[Stage 2b] Rosatom full crawl AES:", len(full_items), "(list rows, no card parse)")
            rosatom_rows = [rosatom_list_to_rows(item) for item in full_items]
        elif keyword_items:
            print("[Stage 2b] Rosatom keyword hits:", len(keyword_items), "(fallback, list rows)")
            rosatom_rows = [rosatom_list_to_rows(item) for item in keyword_items]
        elif discovery.rosatom_aes_filtered:
            print("[Stage 2b] Rosatom discovery list:", len(discovery.rosatom_aes_filtered), "(list rows, no card parse)")
            rosatom_rows = rosatom_lists_to_rows(discovery.rosatom_aes_filtered)
        else:
            rosatom_rows = []
        seen = {(r.get("Notice number"), r.get("Rosatom URL")) for r in all_rows}
        for row in rosatom_rows:
            key = (row.get("Notice number"), row.get("Rosatom URL"))
            if key in seen:
                continue
            seen.add(key)
            all_rows.append(row)
            rosatom_row_count += 1
        print("  Rosatom list rows added:", rosatom_row_count)
    all_rows = normalize_df_columns(all_rows)
    print("Total rows before filter:", len(all_rows))
    if args.skip_bothub:
        kept, rejected = all_rows, []
    else:
        print("[Stage 3] Bothub filter...")
        t1 = time.time()
        kept, rejected = classify_rows(all_rows, discovery.objects)
        print("  keep:", len(kept), "reject:", len(rejected), "in", int(time.time()-t1), "sec")
    if not args.skip_enrich and kept:
        print("[Stage 4] Enrich kept rows (EIS + Rosatom cards)...")
        t2 = time.time()
        kept = enrich_kept_rows(kept, headless=not args.no_headless)
        print("  enriched rows:", len(kept), "in", int(time.time()-t2), "sec")
    kept_df = pd.DataFrame(kept)
    for c in TARGET_COLUMNS:
        if c not in kept_df.columns: kept_df[c] = ""
    kept_df = kept_df[TARGET_COLUMNS]
    rejected_df = pd.DataFrame(rejected)
    for c in REJECTED_COLUMNS:
        if c not in rejected_df.columns: rejected_df[c] = ""
    if len(rejected_df): rejected_df = rejected_df[REJECTED_COLUMNS]
    final_path = out_dir / "final_procurements.xlsx"
    kept_df.to_excel(final_path, index=False)
    if len(rejected_df): rejected_df.to_excel(out_dir / "rejected_procurements.xlsx", index=False)
    summary = {**discovery.stats, "rows_before_filter": len(all_rows), "rows_kept": len(kept_df), "rows_rejected": len(rejected_df), "fabrikant_positions_parsed": fab_pos}
    (out_dir / "pipeline_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("DONE:", final_path, len(kept_df), "rows")
    return 0
if __name__ == "__main__": sys.exit(main())