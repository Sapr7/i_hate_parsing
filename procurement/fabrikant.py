# -*- coding: utf-8 -*-
import re
import urllib.error
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse, parse_qs

from bs4 import BeautifulSoup

from procurement.http_utils import decode_html, fetch_bytes

BASE = "https://www.fabrikant.ru"


def _abs(url: str) -> str:
    if url.startswith("http"):
        return url
    return urljoin(BASE, url)


def extract_lot_id(etp_url: str) -> Optional[str]:
    try:
        html = decode_html(fetch_bytes(etp_url, referer=etp_url))
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, TimeoutError) as exc:
        print(f"    Fabrikant lot_id skip ({etp_url[:80]}...): {exc}")
        return None
    soup = BeautifulSoup(html, "lxml")
    for a in soup.select('a[href*="view_positions"]'):
        href = a.get("href", "")
        qs = parse_qs(urlparse(_abs(href)).query)
        if qs.get("lot_id"):
            return qs["lot_id"][0]
    m = re.search(r"view_positions&lot_id=(\d+)", html)
    return m.group(1) if m else None


def parse_positions(etp_url: str, lot_id: Optional[str] = None) -> List[Dict[str, str]]:
    lot_id = lot_id or extract_lot_id(etp_url)
    if not lot_id:
        return []

    positions: List[Dict[str, str]] = []
    from_offset = 0
    while True:
        url = (
            f"{BASE}/trades/atom/ProposalRequest/?action=view_positions"
            f"&lot_id={lot_id}&lang=RU"
        )
        if from_offset:
            url += f"&from={from_offset}"
        try:
            html = decode_html(fetch_bytes(url, referer=etp_url))
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, TimeoutError) as exc:
            print(f"    Fabrikant positions skip lot_id={lot_id} from={from_offset}: {exc}")
            break
        soup = BeautifulSoup(html, "lxml")
        rows = soup.select("table.blank tbody tr.c1, table.blank tbody tr.c2")
        if not rows:
            break
        for row in rows:
            cols = [td.get_text(" ", strip=True) for td in row.find_all("td")]
            if len(cols) < 4:
                continue
            positions.append(
                {
                    "pos_no": cols[0],
                    "item_name": cols[1],
                    "material_group": cols[2],
                    "quantity": cols[3],
                    "vat_rate": cols[4] if len(cols) > 4 else "",
                    "okpd_hint": _extract_okpd(cols[1]),
                }
            )
        nav = soup.select_one("div.page_nav")
        if not nav:
            break
        next_link = None
        for a in nav.find_all("a", href=True):
            if "Следующая" in a.get_text() or "next" in a.get("href", "").lower():
                next_link = a["href"]
                break
        if not next_link:
            break
        m = re.search(r"from=(\d+)", next_link)
        if not m:
            break
        nxt = int(m.group(1))
        if nxt <= from_offset:
            break
        from_offset = nxt
    return positions


def _extract_okpd(text: str) -> str:
    m = re.search(r"\[(\d{2}(?:\.\d+)+)\]", text)
    return m.group(1) if m else ""
