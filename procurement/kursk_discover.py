# -*- coding: utf-8 -*-
"""Deep EIS discovery for Kursk AES (year-sliced, INN-based)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Tuple

from procurement.eis_client import scan_search_slices, serialize_eis_by_reg

KURSK_OBJECT = "Курская АЭС"
KURSK_OBJECT_2 = "Курская АЭС-2"
KURSK_INN = "4634010454"
KURSK_ORG = 'ООО "Курская АЭС-Сервис"'
DATE_FROM_YEAR = 2020
DATE_TO_YEAR = 2026

# Per-year search plans: (query, require_match, match_object, source_tag)
QUERY_PLANS = [
    (KURSK_OBJECT, True, KURSK_OBJECT, "kursk_query"),
    ("Курская АЭС-Сервис", False, KURSK_OBJECT, "kursk_servis_query"),
    (KURSK_OBJECT_2, True, KURSK_OBJECT_2, "kursk_aes2_query"),
]


def discover_kursk_eis(
    year_from: int = DATE_FROM_YEAR,
    year_to: int = DATE_TO_YEAR,
    max_pages_per_slice: int = 25,
) -> Tuple[Dict[str, dict], dict]:
    by_reg: Dict[str, dict] = {}
    stats = {
        "years": list(range(year_from, year_to + 1)),
        "queries": [],
        "inn": KURSK_INN,
        "total_notices": 0,
    }

    for year in range(year_from, year_to + 1):
        dfrom = f"01.01.{year}"
        dto = f"31.12.{year}"
        print(f"\n=== {year} ===")
        year_added = 0

        for query, require_match, match_obj, source_tag in QUERY_PLANS:
            before = len(by_reg)
            found, pages, total_txt = scan_search_slices(
                by_reg,
                query=query,
                date_from=dfrom,
                date_to=dto,
                max_pages=max_pages_per_slice,
                object_name=KURSK_OBJECT,
                match_object=match_obj,
                require_match=require_match,
                source_tag=source_tag,
                query_tag=f"{query}|{year}",
            )
            added = len(by_reg) - before
            year_added += added
            line = {
                "year": year,
                "query": query,
                "total": total_txt,
                "pages": pages,
                "matched": found,
                "added": added,
            }
            stats["queries"].append(line)
            print(f"  Q {query[:35]:35} total={total_txt:>12} pages={pages:2d} +{added}")
            time.sleep(0.2)

        before = len(by_reg)
        found, pages, total_txt = scan_search_slices(
            by_reg,
            customer_inn=KURSK_INN,
            date_from=dfrom,
            date_to=dto,
            max_pages=max_pages_per_slice,
            object_name=KURSK_OBJECT,
            require_match=False,
            source_tag="kursk_inn",
            query_tag=f"inn:{KURSK_INN}|{year}",
            customer_org=KURSK_ORG,
        )
        added = len(by_reg) - before
        year_added += added
        stats["queries"].append(
            {
                "year": year,
                "query": f"inn:{KURSK_INN}",
                "total": total_txt,
                "pages": pages,
                "matched": found,
                "added": added,
            }
        )
        print(f"  INN {KURSK_INN} total={total_txt:>12} pages={pages:2d} +{added}")
        print(f"  year {year} new unique: {year_added}, cumulative: {len(by_reg)}")

    stats["total_notices"] = len(by_reg)
    return by_reg, stats


def save_kursk_discovery(by_reg: Dict[str, dict], stats: dict, path: Path) -> None:
    payload = {
        "object": KURSK_OBJECT,
        "eis_by_reg": serialize_eis_by_reg(by_reg),
        "stats": stats,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
