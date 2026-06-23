# -*- coding: utf-8 -*-
"""Discover procurements on zakupki.rosatom.ru list pages (Selenium)."""
from __future__ import annotations

import re
import time
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from procurement.rosatom import _make_driver

ROSATOM_LISTS = [
    "https://zakupki.rosatom.ru/?link=completed_procurements",
    "https://zakupki.rosatom.ru/?link=procurements_archive",
    "https://zakupki.rosatom.ru/?link=procurements",
]


def rosatom_number_to_id(number: str) -> str:
    """221129/1065/696 -> 2211291065696"""
    return re.sub(r"\D", "", number or "")


def parse_list_page(html: str, list_source: str) -> List[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows: List[dict] = []
    for tr in soup.select("tr.af-table-body-tr"):
        num_td = tr.select_one('td[id$="-Номер"]')
        if not num_td:
            continue
        number = num_td.get_text(" ", strip=True)
        rid = rosatom_number_to_id(number)
        if len(rid) < 10:
            continue
        subj_td = tr.select_one('td[id$="-ПравоЗаключенияДоговораНа"]')
        org_td = tr.select_one('td[id$="-ОрганизаторЗакупки"]')
        stat_td = tr.select_one('td[id$="-РасширенныйСтатус"]')
        price_td = tr.select_one('td[id$="-НМЦЛотов"]')
        date_td = tr.select_one('td[id$="-Дата"]')
        rows.append(
            {
                "rosatom_number": number,
                "rosatom_id": rid,
                "url": (
                    f"https://zakupki.rosatom.ru/{rid}"
                    f"?link=procurements_archive&obj_id={rid}"
                ),
                "subject": subj_td.get_text(" ", strip=True) if subj_td else "",
                "organizer": org_td.get_text(" ", strip=True) if org_td else "",
                "status": stat_td.get_text(" ", strip=True) if stat_td else "",
                "price_rub": price_td.get_text(" ", strip=True) if price_td else "",
                "publish_date": date_td.get_text(" ", strip=True) if date_td else "",
                "list_source": list_source,
                "source": "rosatom_list",
            }
        )
    return rows


def discover_rosatom_rows(
    list_urls: Optional[List[str]] = None,
    *,
    headless: bool = True,
    wait_sec: int = 12,
    scroll_times: int = 3,
    max_pages_per_list: int = 1,
) -> Dict[str, dict]:
    """
    Parse visible Rosatom list tables.
    Returns {rosatom_id: row_dict}.
    """
    list_urls = list_urls or ROSATOM_LISTS
    driver = _make_driver(headless=headless)
    found: Dict[str, dict] = {}
    try:
        driver.set_page_load_timeout(90)
        for list_url in list_urls:
            driver.get(list_url)
            time.sleep(wait_sec)
            if "Техническая поддержка" in (driver.title or ""):
                continue
            for _ in range(scroll_times):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            for page in range(max_pages_per_list):
                html = driver.page_source
                for row in parse_list_page(html, list_url):
                    found.setdefault(row["rosatom_id"], row)
                if page + 1 >= max_pages_per_list:
                    break
                # pagination: best-effort click "next" if present
                next_btns = driver.find_elements(
                    "css selector", "div.paginator button, div.paginator a"
                )
                clicked = False
                for btn in next_btns:
                    label = (btn.text or "").strip().lower()
                    if label in {">", "›", "next", "след"}:
                        btn.click()
                        time.sleep(wait_sec)
                        clicked = True
                        break
                if not clicked:
                    break
    finally:
        driver.quit()
    return found


# Backward-compatible alias
def discover_rosatom_ids(*args, **kwargs) -> Dict[str, dict]:
    return discover_rosatom_rows(*args, **kwargs)
