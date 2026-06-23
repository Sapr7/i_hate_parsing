# -*- coding: utf-8 -*-
"""Parse OKPD2 / OKVED2 rows from EIS lot-list (separate columns, split codes)."""
from __future__ import annotations

import re
from typing import Dict, List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from procurement.eis_client import fetch

BASE = "https://zakupki.gov.ru"
CODE_RE = re.compile(r"(\d{2}(?:\.\d+)+)\.?\d*\s*([^0-9\n\r;|]+?)(?=\s*\d{2}(?:\.\d+)|$)", re.S)


def split_classifier(text: str) -> List[str]:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return []
    parts = []
    for m in CODE_RE.finditer(text):
        code = m.group(1)
        desc = m.group(2).strip(" ,.;")
        parts.append(f"{code} {desc}".strip())
    if parts:
        return parts
    return [text] if text else []


def parse_lot_list(reg: str, guid: str) -> List[Dict[str, str]]:
    if not guid:
        return []
    url = (
        f"{BASE}/epz/order/notice/notice223/lot-list.html"
        f"?purchaseNoticeNumber={reg}&noticeGuid={guid}"
    )
    html = fetch(url, timeout=45)
    soup = BeautifulSoup(html, "lxml")
    rows: List[Dict[str, str]] = []

    for tr in soup.select("table tr"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        texts = [td.get_text(" ", strip=True) for td in tds]
        first = texts[0]
        if not first or first.startswith("№") or "Критерий" in first:
            continue
        lot_name = re.sub(r"^\d+\s*", "", first).strip()
        okpd_raw = texts[3] if len(texts) > 3 else ""
        okved_raw = texts[4] if len(texts) > 4 else ""
        lot_url = ""
        a = tr.select_one("a[href*=lot-info]")
        if a:
            lot_url = urljoin(BASE, a.get("href", ""))
        if not okpd_raw and not okved_raw:
            continue

        okpd_list = split_classifier(okpd_raw)
        okved_list = split_classifier(okved_raw)
        n = max(len(okpd_list), len(okved_list), 1)
        for i in range(n):
            rows.append(
                {
                    "lot_name": lot_name,
                    "okpd": okpd_list[i] if i < len(okpd_list) else (okpd_list[0] if okpd_list else ""),
                    "okved": okved_list[i] if i < len(okved_list) else (okved_list[0] if okved_list else ""),
                    "lot_url": lot_url,
                }
            )
    return rows
