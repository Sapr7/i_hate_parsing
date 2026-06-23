# -*- coding: utf-8 -*-
"""Parse dates and header fields from EIS epz common-info."""
from __future__ import annotations

import re
from typing import Dict

from bs4 import BeautifulSoup

from procurement.eis_client import fetch

DATE_RE = re.compile(r"(\d{2}\.\d{2}\.\d{4}(?:\s+\d{2}:\d{2})?)")
BASE = "https://zakupki.gov.ru"

LABELS = {
    "publish_date": ("размещено", "дата публикации извещения"),
    "application_start": ("начало срока подачи", "дата начала срока подачи"),
    "deadline_date": ("окончание подачи заявок", "окончания срока подачи"),
}


def _line_date(lines, idx: int) -> str:
    for j in (idx, idx + 1, idx + 2):
        if j >= len(lines):
            break
        m = DATE_RE.search(lines[j])
        if m:
            return m.group(1)
    return ""


def parse_epz_dates(html: str) -> Dict[str, str]:
    lines = [ln.strip() for ln in BeautifulSoup(html, "lxml").get_text("\n", strip=True).split("\n") if ln.strip()]
    out = {k: "" for k in LABELS}
    for i, ln in enumerate(lines):
        low = ln.lower()
        for key, keywords in LABELS.items():
            if out[key]:
                continue
            if any(kw in low for kw in keywords) and len(ln) < 150:
                out[key] = _line_date(lines, i)
    return out


def fetch_epz_common(reg: str, guid: str) -> str:
    url = f"{BASE}/epz/order/notice/notice223/common-info.html?noticeGuid={guid}&regNumber={reg}"
    return fetch(url, timeout=45)


def parse_notice_dates(reg: str, entry_html: str, guid: str = "") -> Dict[str, str]:
    if guid:
        try:
            return parse_epz_dates(fetch_epz_common(reg, guid))
        except Exception:
            pass
    return parse_epz_dates(entry_html)
