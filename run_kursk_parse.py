#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parse Kursk AES EIS notices: dates, OKPD/OKVED, positions from all sources."""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from procurement.detail_merge import merge_notice_details
from procurement.eis_client import fetch
from procurement.eis_sources import discover_eis_sources, sources_to_row_fields
from procurement.enrich import eis_to_rows
from procurement.schema import TARGET_COLUMNS

EXTRA_COLUMNS = [
    "OKPD",
    "OKVED",
    "Application start date",
    "Position source",
    "EIS documents URL",
    "Document links",
    "Source notes",
    "Parse notes",
]


def load_kursk(discovery_path: Path):
    disc = json.loads(discovery_path.read_text(encoding="utf-8"))
    by_reg = disc.get("eis_by_reg") or disc
    rows = []
    for reg, item in by_reg.items():
        if not isinstance(item, dict):
            continue
        objs = item.get("matched_objects") or []
        source = str(item.get("source") or "")
        title = str(item.get("title") or "")
        customer = str(item.get("customer") or "")
        is_kursk = (
            any("Курск" in str(o) for o in objs)
            or source.startswith("kursk_")
            or "курск" in title.lower()
            or "курск" in customer.lower()
        )
        if not is_kursk:
            continue
        url = item.get("url") or (
            f"https://zakupki.gov.ru/223/purchase/public/purchase/info/common-info.html?regNumber={reg}"
        )
        rows.append({"reg": reg, "item": item, "url": url})
    rows.sort(key=lambda x: x["reg"])
    return rows


def _save_checkpoint(path: Path, done_regs: list, all_rows: list) -> None:
    ck = path.with_suffix(".checkpoint.json")
    ck.write_text(
        json.dumps({"done_regs": done_regs, "rows": all_rows}, ensure_ascii=False),
        encoding="utf-8",
    )


def _load_checkpoint(path: Path):
    ck = path.with_suffix(".checkpoint.json")
    if not ck.is_file():
        return [], []
    data = json.loads(ck.read_text(encoding="utf-8"))
    return data.get("done_regs") or [], data.get("rows") or []


def _write_output(out: Path, all_rows: list, notice_count: int) -> dict:
    cols = TARGET_COLUMNS + [c for c in EXTRA_COLUMNS if c not in TARGET_COLUMNS]
    df = pd.DataFrame(all_rows)
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    if len(df):
        df = df[cols]
    df.to_excel(out, index=False)
    summary = {
        "notices": notice_count,
        "parsed_notices": len({r.get("Notice number") for r in all_rows if r.get("Notice number")}),
        "output_rows": len(df),
        "with_okpd": int((df["OKPD"].astype(str).str.strip() != "").sum()) if len(df) else 0,
        "with_okved": int((df["OKVED"].astype(str).str.strip() != "").sum()) if len(df) else 0,
        "with_qty": int((df["Quantity"].astype(str).str.strip() != "").sum()) if len(df) else 0,
        "with_deadline": int((df["Deadline date"].astype(str).str.strip() != "").sum()) if len(df) else 0,
    }
    out.with_suffix(".summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--discovery", default="output/kursk_discovery_cache.json")
    ap.add_argument("--out", default="output/kursk_eis_parsed_v3.xlsx")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--checkpoint-every", type=int, default=25)
    ap.add_argument("--kept-regs", default="", help="JSON list of reg numbers after Bothub filter")
    args = ap.parse_args()

    items = load_kursk(Path(args.discovery))
    if args.kept_regs:
        kept = set(json.loads(Path(args.kept_regs).read_text(encoding="utf-8")))
        items = [x for x in items if x["reg"] in kept]
    if args.limit:
        items = items[: args.limit]

    out = Path(args.out)
    done_regs, all_rows = ([], [])
    if args.resume:
        done_regs, all_rows = _load_checkpoint(out)
        done_regs = list(done_regs)
    done_set = set(done_regs)

    pending = [x for x in items if x["reg"] not in done_set]
    print("Kursk parse:", len(items), "pending:", len(pending), "resume:", len(done_set))

    errors = []
    for i, row in enumerate(pending, 1):
        reg = row["reg"]
        pos = len(done_set) + i
        print(f"  [{pos}/{len(items)}] {reg}")
        try:
            entry_html = fetch(row["url"], timeout=45)
            src = discover_eis_sources(reg, row["url"])
            link_fields = sources_to_row_fields(src)
            base = eis_to_rows({reg: row["item"]})[0]
            base.update(link_fields)
            detail_rows = merge_notice_details(reg, entry_html, src)
            for dr in detail_rows:
                merged = {**base, **dr}
                merged["Publish date"] = dr.get("Publish date") or merged.get("Publish date", "")
                merged["Deadline date"] = dr.get("Deadline date") or merged.get("Deadline date", "")
                all_rows.append(merged)
            done_set.add(reg)
            done_regs.append(reg)
        except Exception as exc:
            errors.append({"reg": reg, "error": str(exc)})
            print(f"    ERROR {reg}: {exc}")

        if i % args.checkpoint_every == 0:
            _save_checkpoint(out, done_regs, all_rows)
            _write_output(out, all_rows, len(items))
            print(f"    checkpoint {len(done_set)}/{len(items)} rows={len(all_rows)}")

    _save_checkpoint(out, done_regs, all_rows)
    summary = _write_output(out, all_rows, len(items))
    if errors:
        out.with_suffix(".errors.json").write_text(
            json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print("DONE", out, summary, "errors:", len(errors))
    return 0


if __name__ == "__main__":
    sys.exit(main())
