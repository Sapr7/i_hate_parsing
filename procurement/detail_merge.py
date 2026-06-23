# -*- coding: utf-8 -*-
"""Merge procurement details from ETP, documents, EIS lot table."""
from __future__ import annotations

from typing import Dict, List

from procurement.doc_parse import parse_documents, score_document_rows
from procurement.eis_epz_parse import parse_notice_dates
from procurement.eis_lot_parse import parse_lot_list
from procurement.fabrikant import parse_positions


def _etp_positions(platform_url: str) -> List[Dict[str, str]]:
    if not platform_url or "fabrikant" not in platform_url.lower():
        return []
    try:
        pos = parse_positions(platform_url)
    except Exception:
        return []
    rows = []
    for p in pos:
        item = (p.get("item_name") or p.get("material_group") or "").strip()
        if not item:
            continue
        rows.append(
            {
                "item": item,
                "quantity": p.get("quantity", ""),
                "price_for_one": "",
                "okpd": p.get("okpd_hint", ""),
                "source": "fabrikant",
            }
        )
    return rows


def merge_notice_details(reg: str, entry_html: str, sources: Dict) -> List[Dict]:
    guid = sources.get("notice_guid") or ""
    dates = parse_notice_dates(reg, entry_html, guid)
    lots = parse_lot_list(reg, guid)

    etp_url = sources.get("primary_etp_url") or ""
    docs = sources.get("document_links") or []
    docs_page = (sources.get("eis_pages") or {}).get("eis_documents", "")

    positions = _etp_positions(etp_url)
    pos_source = ""
    doc_title = ""

    if positions:
        pos_source = "etp"
    else:
        positions = parse_documents(docs, docs_page)
        doc_score = score_document_rows(positions)
        if positions and lots and doc_score < 15:
            positions = []
        elif positions:
            pos_source = "documents"
            doc_title = positions[0].get("source", "")

    notes = []
    if dates.get("publish_date"):
        notes.append(f"Publish: {dates['publish_date']}")
    if dates.get("application_start"):
        notes.append(f"Start: {dates['application_start']}")
    if dates.get("deadline_date"):
        notes.append(f"End: {dates['deadline_date']}")
    if lots:
        notes.append(f"OKPD/OKVED: lot-list ({len(lots)} codes)")
    if pos_source == "etp":
        notes.append(f"Positions: fabrikant ({len(positions)})")
    elif pos_source == "documents":
        notes.append(f"Positions: {doc_title} ({len(positions)} rows)")
    elif lots:
        notes.append("Positions: only lot-list (no qty/price)")
    else:
        notes.append("Positions: not found")

    header = {
        "Publish date": dates.get("publish_date", ""),
        "Application start date": dates.get("application_start", ""),
        "Deadline date": dates.get("deadline_date", ""),
        "Parse notes": " | ".join(notes),
    }

    if positions:
        out = []
        lot0 = lots[0] if lots else {}
        for p in positions:
            row = dict(header)
            row["Item"] = p.get("item", "")
            row["Quantity"] = p.get("quantity", "")
            row["Price for 1 piece"] = p.get("price_for_one", "")
            row["OKPD"] = p.get("okpd") or lot0.get("okpd", "")
            row["OKVED"] = lot0.get("okved", "")
            row["Position source"] = p.get("source", pos_source)
            out.append(row)
        return out

    if lots:
        out = []
        for lot in lots:
            row = dict(header)
            row["Item"] = lot.get("lot_name", "")
            row["OKPD"] = lot.get("okpd", "")
            row["OKVED"] = lot.get("okved", "")
            row["Position source"] = "lot-list"
            out.append(row)
        return out

    return [{**header, "Position source": "none"}]
