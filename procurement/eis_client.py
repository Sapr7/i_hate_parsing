# -*- coding: utf-8 -*-
"""EIS (zakupki.gov.ru) search client."""
from __future__ import annotations

import re
import ssl
import time
import urllib.parse
import urllib.request
from typing import Dict, List, Tuple

from procurement.matching import loose_match, object_tokens

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DATE_FROM = "01.01.2020"
DATE_TO = "31.12.2026"
MAX_PAGES = 8


def _store_card(
    by_reg: Dict[str, dict],
    card: Dict[str, str],
    *,
    source_tag: str,
    object_name: str,
    query_tag: str,
    customer_inn: str = "",
    customer_org: str = "",
) -> None:
    item = by_reg.setdefault(
        card["reg"],
        {
            **card,
            "source": source_tag,
            "matched_objects": set(),
            "queries": set(),
        },
    )
    if customer_inn:
        item["customer_inn"] = customer_inn
    if customer_org:
        item["customer_filter_org"] = customer_org
    item["matched_objects"].add(object_name)
    item["queries"].add(query_tag)
    for key, val in card.items():
        if val:
            item[key] = val


def serialize_eis_by_reg(by_reg: Dict[str, dict]) -> Dict[str, dict]:
    out = {}
    for reg, item in by_reg.items():
        row = dict(item)
        mos = row.get("matched_objects") or []
        qs = row.get("queries") or []
        row["matched_objects"] = sorted(mos) if isinstance(mos, set) else list(mos)
        row["queries"] = sorted(qs) if isinstance(qs, set) else list(qs)
        out[reg] = row
    return out


def fetch(url: str, timeout: int = 30, retries: int = 4) -> str:
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.9"},
            )
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as err:
            last_err = err
            time.sleep(1.2 * (attempt + 1))
    raise last_err


def build_url(
    query: str = "",
    page: int = 1,
    customer_inn: str = "",
    date_from: str | None = None,
    date_to: str | None = None,
    sort_by: str = "UPDATE_DATE",
    sort_desc: bool = True,
) -> str:
    params = {
        "searchString": query,
        "morphology": "on",
        "search-filter": "Дате размещения",
        "pageNumber": str(page),
        "sortDirection": "true" if sort_desc else "false",
        "recordsPerPage": "_50",
        "showLotsInfoHidden": "false",
        "sortBy": sort_by,
        "fz44": "on",
        "fz223": "on",
        "pc": "on",
        "currencyIdGeneral": "-1",
        "publishDateFrom": date_from or DATE_FROM,
        "publishDateTo": date_to or DATE_TO,
    }
    if customer_inn:
        params["customerInn"] = customer_inn
    return (
        "https://zakupki.gov.ru/epz/order/extendedsearch/results.html?"
        + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    )


def parse_total(html: str) -> Tuple[int | None, str]:
    m = re.search(r"search-results__total[^>]*>(.*?)</", html, re.S)
    if not m:
        return None, "?"
    text = re.sub(r"\s+", " ", m.group(1)).strip()
    if "более" in text.lower():
        return None, text
    digits = re.sub(r"\D", "", text)
    return (int(digits) if digits else None), text


def parse_cards(html: str) -> List[Dict[str, str]]:
    cards = []
    for block in re.split(r"registry-entry__form", html)[1:]:
        reg_m = re.search(r"regNumber=(\d+)", block)
        if not reg_m:
            continue
        reg = reg_m.group(1)
        title = ""
        obj_m = re.search(
            r"Объект закупки[\s\S]{0,220}?registry-entry__body-value[^>]*>(.*?)</div>",
            block,
            re.S,
        )
        if obj_m:
            title = re.sub(r"\s+", " ", re.sub(r"<.*?>", " ", obj_m.group(1))).strip()
        if not title:
            for pat in (
                r"registry-entry__body-value[^>]*>\s*<a[^>]*>(.*?)</a>",
                r"registry-entry__body-value[^>]*>(.*?)</div>",
            ):
                sm = re.search(pat, block, re.S)
                if sm:
                    title = re.sub(r"\s+", " ", re.sub(r"<.*?>", " ", sm.group(1))).strip()
                    if title:
                        break
        cust = ""
        cm = re.search(
            r"Заказчик[\s\S]{0,500}?registry-entry__body-href[^>]*>\s*<a[^>]*>(.*?)</a>",
            block,
            re.S,
        )
        if cm:
            cust = re.sub(r"\s+", " ", re.sub(r"<.*?>", " ", cm.group(1))).strip()
        href_m = re.search(
            r'href="(https://zakupki\.gov\.ru[^"]*regNumber=\d+[^"]*)"',
            block,
        )
        cards.append(
            {
                "reg": reg,
                "title": title,
                "customer": cust,
                "url": href_m.group(1).replace("&amp;", "&") if href_m else "",
            }
        )
    return cards


def scan_search_slices(
    by_reg: Dict[str, dict],
    *,
    query: str = "",
    customer_inn: str = "",
    date_from: str,
    date_to: str,
    max_pages: int = 25,
    object_name: str = "",
    match_object: str | None = None,
    require_match: bool = True,
    source_tag: str = "eis",
    query_tag: str = "",
    customer_org: str = "",
    sort_by: str = "PUBLISH_DATE",
) -> Tuple[int, int, str]:
    """Scan one date slice; return matched_count, pages_scanned, total_text."""
    match_object = match_object or object_name or query
    tag = query_tag or query or f"inn:{customer_inn}"
    first_html = fetch(
        build_url(
            query=query,
            customer_inn=customer_inn,
            date_from=date_from,
            date_to=date_to,
            sort_by=sort_by,
            sort_desc=False,
        )
    )
    total_num, total_txt = parse_total(first_html)
    if total_num == 0:
        return 0, 0, total_txt
    if total_num is None:
        pages = max_pages
    else:
        pages = min(max_pages, (total_num + 49) // 50)

    found = 0
    for page in range(1, pages + 1):
        html = (
            first_html
            if page == 1
            else fetch(
                build_url(
                    query=query,
                    page=page,
                    customer_inn=customer_inn,
                    date_from=date_from,
                    date_to=date_to,
                    sort_by=sort_by,
                    sort_desc=False,
                )
            )
        )
        for card in parse_cards(html):
            if require_match and not loose_match(card["title"], match_object):
                continue
            _store_card(
                by_reg,
                card,
                source_tag=source_tag,
                object_name=object_name or match_object,
                query_tag=tag,
                customer_inn=customer_inn,
                customer_org=customer_org,
            )
            found += 1
        if page < pages:
            time.sleep(0.12)
    return found, pages, total_txt


def scan_query_loose(
    query: str,
    object_name: str,
    by_reg: Dict[str, dict],
    *,
    match_object: str | None = None,
    source_tag: str = "eis_object",
) -> Tuple[int, str]:
    """Collect cards where loose_match passes for object_name."""
    match_object = match_object or object_name
    first_html = fetch(build_url(query))
    total_num, total_txt = parse_total(first_html)
    if total_num == 0:
        return 0, total_txt
    pages = 1
    if total_num is not None and total_num > 0:
        pages = min(MAX_PAGES, (total_num + 49) // 50)

    found = 0
    for page in range(1, pages + 1):
        html = first_html if page == 1 else fetch(build_url(query, page=page))
        for card in parse_cards(html):
            if not loose_match(card["title"], match_object):
                continue
            item = by_reg.setdefault(
                card["reg"],
                {
                    **card,
                    "source": source_tag,
                    "matched_objects": set(),
                    "queries": set(),
                },
            )
            item["matched_objects"].add(object_name)
            item["queries"].add(query)
            found += 1
        if page < pages:
            time.sleep(0.15)
    return found, total_txt


def scan_customer_inn(
    inn: str,
    org_name: str,
    objects: List[str],
    by_reg: Dict[str, dict],
) -> Tuple[int, str]:
    """All EIS notices for customer INN; tag matching AES objects loosely."""
    first_html = fetch(build_url(customer_inn=inn))
    total_num, total_txt = parse_total(first_html)
    if total_num == 0:
        return 0, total_txt
    pages = min(MAX_PAGES, ((total_num or 0) + 49) // 50) if total_num else 1

    found = 0
    for page in range(1, pages + 1):
        html = first_html if page == 1 else fetch(build_url(customer_inn=inn, page=page))
        for card in parse_cards(html):
            matched = [o for o in objects if loose_match(card["title"], o)]
            # Keep all atom-customer notices in loose pool; reasoning filter later.
            item = by_reg.setdefault(
                card["reg"],
                {
                    **card,
                    "source": "eis_customer_inn",
                    "matched_objects": set(),
                    "queries": set(),
                    "customer_inn": inn,
                    "customer_filter_org": org_name,
                },
            )
            for o in matched:
                item["matched_objects"].add(o)
            item["queries"].add(f"inn:{inn}")
            found += 1
        if page < pages:
            time.sleep(0.15)
    return found, total_txt


def object_search_queries(object_name: str) -> List[str]:
    queries = [object_name]
    for tok in object_tokens(object_name)[1:4]:
        queries.append(tok)
    seen = set()
    out = []
    for q in queries:
        key = q.lower()
        if key not in seen:
            seen.add(key)
            out.append(q)
    return out
