#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Collect EIS source links for Kursk AES notices (EIS only, no Rosatom)."""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from procurement.eis_sources import discover_eis_sources, sources_to_row_fields
from procurement.enrich import eis_to_rows
from procurement.schema import TARGET_COLUMNS

SOURCE_COLUMNS = [
    "EIS documents URL",
    "Document links",
    "Source notes",
]


def load_kursk_eis(discovery_path: Path):
    disc = json.loads(discovery_path.read_text(encoding="utf-8"))
    rows = []
    for reg, item in disc.get("eis_by_reg", {}).items():
        objs = item.get("matched_objects") or []
        if not any("Курск" in str(o) for o in objs):
            continue
        url = item.get("url") or (
            f"https://zakupki.gov.ru/223/purchase/public/purchase/info/common-info.html?regNumber={reg}"
        )
        rows.append({"reg": reg, "item": item, "url": url})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--discovery", default="output/discovery_cache.json")
    ap.add_argument("--out", default="output/kursk_eis_sources.xlsx")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    items = load_kursk_eis(Path(args.discovery))
    if args.limit:
        items = items[: args.limit]
    print("Kursk EIS notices:", len(items))

    out_rows = []
    stats = {"etp": 0, "docs": 0, "both": 0, "neither": 0, "platforms": {}}
    for i, row in enumerate(items, 1):
        reg = row["reg"]
        print(f"  [{i}/{len(items)}] {reg}")
        src = discover_eis_sources(reg, row["url"])
        fields = sources_to_row_fields(src)

        base = eis_to_rows({reg: row["item"]})[0]
        base.update(fields)
        base["Platform URL"] = fields.get("Platform URL") or base.get("Platform URL", "")
        out_rows.append(base)

        has_etp = bool(src.get("etp_links"))
        has_docs = bool(src.get("document_links"))
        if has_etp:
            stats["etp"] += 1
        if has_docs:
            stats["docs"] += 1
        if has_etp and has_docs:
            stats["both"] += 1
        if not has_etp and not has_docs:
            stats["neither"] += 1
        for p in src.get("etp_platforms") or []:
            stats["platforms"][p] = stats["platforms"].get(p, 0) + 1

    cols = TARGET_COLUMNS + [c for c in SOURCE_COLUMNS if c not in TARGET_COLUMNS]
    df = pd.DataFrame(out_rows)
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df = df[cols]
    out = Path(args.out)
    df.to_excel(out, index=False)
    summary = {"notices": len(items), **stats}
    out.with_suffix(".summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("DONE", out, summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
