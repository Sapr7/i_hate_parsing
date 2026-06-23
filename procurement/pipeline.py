# -*- coding: utf-8 -*-
from typing import Dict, List, Optional

import pandas as pd

from procurement.fabrikant import parse_positions
from procurement.rosatom import parse_procurement


OUTPUT_COLUMNS = [
    "rosatom_number",
    "status",
    "price_rub",
    "eis_url",
    "etp_url",
    "organizer",
    "application_start",
    "results_date",
    "publish_date",
    "subject",
    "source_url",
    "pos_no",
    "item_name",
    "material_group",
    "quantity",
    "okpd_hint",
]


def parse_rosatom_to_rows(
    rosatom_url: str,
    headless: bool = True,
) -> List[Dict[str, str]]:
    header = parse_procurement(rosatom_url, headless=headless)
    etp = header.get("etp_url", "")
    positions: List[Dict[str, str]] = []
    if etp:
        positions = parse_positions(etp)
    if not positions:
        positions = [{"pos_no": "", "item_name": "", "material_group": "", "quantity": "", "okpd_hint": ""}]
    rows = []
    base = {
        "rosatom_number": header.get("rosatom_number", ""),
        "status": header.get("status", ""),
        "price_rub": header.get("price_rub", ""),
        "eis_url": header.get("eis_url", ""),
        "etp_url": header.get("etp_url", ""),
        "organizer": header.get("organizer", ""),
        "application_start": header.get("application_start", ""),
        "results_date": header.get("results_date", ""),
        "publish_date": header.get("publish_date", ""),
        "subject": header.get("subject", header.get("page_title", "")),
        "source_url": header.get("source_url", rosatom_url),
    }
    for pos in positions:
        row = {**base, **pos}
        rows.append(row)
    return rows


def export_rows(rows: List[Dict[str, str]], path: str) -> None:
    df = pd.DataFrame(rows)
    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[OUTPUT_COLUMNS]
    df.to_excel(path, index=False)
