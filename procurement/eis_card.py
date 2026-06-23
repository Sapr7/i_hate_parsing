# -*- coding: utf-8 -*-
"""Parse EIS notice card (common-info) for dates and price."""
from __future__ import annotations

import re
from typing import Dict

from bs4 import BeautifulSoup

from procurement.eis_client import fetch

DATE_RE = re.compile(r"\b(\d{2}\.\d{2}\.\d{4})\b")
PRICE_RE = re.compile(r"\d{1,3}(?:[ \u00a0\u202f]\d{3})*,\d{2}")


def _find_date(text: str, *keywords: str) -> str:
    low = (text or "").lower()
    if not any(k in low for k in keywords):
        return ""
    m = DATE_RE.search(text)
    return m.group(1) if m else ""


def parse_eis_card(url: str) -> Dict[str, str]:
    if not url:
        return {}
    try:
        html = fetch(url, timeout=45)
    except Exception:
        return {}
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)

    initial_price = ""
    for sel in [".cardMainInfo__content.cost", ".price-block__value", ".cardMainInfo__content"]:
        node = soup.select_one(sel)
        if node:
            m = PRICE_RE.search(node.get_text(" ", strip=True))
            if m:
                initial_price = m.group(0)
                break
    if not initial_price:
        m = PRICE_RE.search(text)
        if m:
            initial_price = m.group(0)

    publish_date = ""
    deadline_date = ""
    contract_date = ""
    for block in soup.select("section.blockInfo, div.cardMainInfo__section, div.blockInfo__section"):
        bt = block.get_text(" ", strip=True)
        low = bt.lower()
        if not publish_date and ("@07<5I" in low or ">?C1;8:" in low):
            publish_date = _find_date(bt, "@07<5I", ">?C1;8:")
        if not deadline_date and (">:>=G0=" in low or "?>40G" in low):
            deadline_date = _find_date(bt, ">:>=G0=", "?>40G")
        if not contract_date and "8A?>;=5=" in low and ":>=B@0:B" in low:
            contract_date = _find_date(bt, "8A?>;=5=", ":>=B@0:B")

    customer = ""
    a = soup.select_one('a[href*="/customer/"]')
    if a:
        customer = a.get_text(" ", strip=True)

    lot = ""
    m = re.search(r"!\s*(\d{4,}/\d+/\d+)", text)
    if m:
        lot = m.group(1)

    return {
        "initial_price": initial_price,
        "publish_date": publish_date,
        "deadline_date": deadline_date,
        "contract_execution_date": contract_date,
        "customer_name": customer,
        "supplier_number": lot,
    }
