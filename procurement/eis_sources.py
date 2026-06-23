# -*- coding: utf-8 -*-
"""Discover detail source links on EIS notice cards (links only, no content parse)."""
from __future__ import annotations

import re
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from procurement.eis_client import fetch

BASE = "https://zakupki.gov.ru"

ETP_PATTERNS = (
    ("fabrikant", ("fabrikant.ru",)),
    ("rts_tender", ("rts-tender.ru", "rts.ru")),
    ("sberbank_ast", ("sberbank-ast.ru", "utp.sberbank-ast.ru")),
    ("roseltorg", ("roseltorg.ru", "roseltorg.com")),
    ("etpgpb", ("etpgpb.ru", "etpgpb.com")),
    ("tektorg", ("tektorg.ru",)),
    ("etp_eis", ("etp.zakupki.gov.ru",)),
    ("lot_online", ("lot-online.ru",)),
    ("synapse", ("synapse.ru",)),
    ("bidzaar", ("bidzaar.com",)),
)

EIS_TAB_SUFFIXES = (
    "common-info.html",
    "documents.html",
    "lot-list.html",
    "lot/lot-info.html",
    "protocols.html",
    "contract-info.html",
    "changes-and-explanations.html",
    "event-journal.html",
)

DOC_RE = re.compile(r"filestore|/download/|\.(?:docx?|xlsx?|pdf|zip|rar)(?:\?|$)", re.I)
TRADE_PATH_RE = re.compile(
    r"/(?:trades|trade|procedure|procedures|lot|lots|purchase|tender|auction|view|order)[/\?]",
    re.I,
)
FOOTER_HOSTS = {
    "www.fas.gov.ru", "www.economy.gov.ru", "www.government.ru", "www.kremlin.ru",
    "minfin.gov.ru", "roskazna.gov.ru", "www.astgoz.ru", "etprf.ru", "etp.zakazrf.ru",
    "gosuslugi.ru", "zakupki.gov.ru",
}
CARD_PLATFORM_LABELS = (
    "адрес электронной площадки",
    "наименование электронной площадки",
)


def abs_url(href: str, page_url: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return urljoin(page_url, href)


def classify_etp(url: str) -> Optional[str]:
    low = url.lower()
    for name, domains in ETP_PATTERNS:
        if any(d in low for d in domains):
            return name
    host = urlparse(url).netloc.lower()
    if host.startswith("atom") and "roseltorg" in host:
        return "roseltorg_atom"
    if host and host not in FOOTER_HOSTS and "zakupki.gov.ru" not in host:
        return f"other:{host}"
    return None


def _is_homepage(url: str) -> bool:
    p = urlparse(url)
    path = (p.path or "/").strip("/")
    return not path or path in ("index.html", "index.php")


def _is_footer_link(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host in FOOTER_HOSTS


def _is_trade_url(url: str) -> bool:
    if _is_homepage(url) or _is_footer_link(url):
        return False
    low = url.lower()
    if TRADE_PATH_RE.search(low):
        return True
    if "atom" in urlparse(url).netloc.lower() and "roseltorg" in low:
        return True
    if any(x in low for x in ("?id=", "&id=", "lot_id=", "procedure=", "regnumber=")):
        return True
    return False


def _parse_card_platform(html: str) -> List[Dict[str, str]]:
    """ETP name/URL from structured card fields (not site footer)."""
    soup = BeautifulSoup(html, "lxml")
    main = soup.select_one("#cardContent, .card-notice-content, .notice-card-content, main")
    text = (main or soup).get_text("\n", strip=True)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    found: List[Dict[str, str]] = []
    for i, ln in enumerate(lines):
        low = ln.lower()
        if not any(lbl in low for lbl in CARD_PLATFORM_LABELS):
            continue
        for nxt in lines[i + 1 : i + 4]:
            if nxt.lower().startswith("http"):
                plat = classify_etp(nxt) or "unknown"
                found.append(
                    {
                        "title": "card_platform_address",
                        "url": nxt,
                        "platform": plat,
                        "source": "eis_card_field",
                    }
                )
                break
    for m in re.finditer(r"(https?://atom[\w.-]*roseltorg[\w./?=&%-]+)", text, re.I):
        url = m.group(1).rstrip(").,;")
        plat = classify_etp(url) or "roseltorg_atom"
        found.append(
            {"title": "atom_roseltorg", "url": url, "platform": plat, "source": "eis_card_text"}
        )
    seen = set()
    out = []
    for item in found:
        if item["url"] not in seen:
            seen.add(item["url"])
            out.append(item)
    return out


def _extract_guid(html: str) -> str:
    m = re.search(r"noticeGuid=([0-9a-f-]{36})", html, re.I)
    return m.group(1) if m else ""


def epz_urls(reg: str, guid: str) -> Dict[str, str]:
    if not guid:
        return {}
    q = f"purchaseNoticeNumber={reg}&noticeGuid={guid}"
    return {
        "eis_common_info_epz": f"{BASE}/epz/order/notice/notice223/common-info.html?noticeGuid={guid}&regNumber={reg}",
        "eis_documents": f"{BASE}/epz/order/notice/notice223/documents.html?{q}",
        "eis_lot_list": f"{BASE}/epz/order/notice/notice223/lot-list.html?{q}",
        "eis_protocols": f"{BASE}/epz/order/notice/notice223/protocols.html?{q}",
        "eis_contract_info": f"{BASE}/epz/order/notice/notice223/contract-info.html?{q}",
        "eis_changes": f"{BASE}/epz/order/notice/notice223/changes-and-explanations.html?{q}",
    }


def _scan_page(html: str, page_url: str) -> Dict[str, List[Dict[str, str]]]:
    soup = BeautifulSoup(html, "lxml")
    out = {
        "eis_tabs": [],
        "etp_links": [],
        "document_links": [],
        "lot_links": [],
        "other_links": [],
    }
    seen = set()
    for a in soup.select("a[href]"):
        href = abs_url(a.get("href", ""), page_url)
        if not href or href in seen:
            continue
        seen.add(href)
        title = a.get_text(" ", strip=True)[:120] or href.split("/")[-1][:80]
        low = href.lower()

        if DOC_RE.search(low):
            if "filestore" in low or "/223/" in low or "document" in page_url:
                if "zakupki-traffic" in low or "/rpt/" in low:
                    continue
                out["document_links"].append({"title": title, "url": href, "kind": _doc_kind(low)})
            continue

        if "lot-info.html" in low or "/lot/lot-info" in low:
            out["lot_links"].append({"title": title, "url": href})
            continue

        if any(suffix in low for suffix in EIS_TAB_SUFFIXES):
            out["eis_tabs"].append({"title": title, "url": href})
            continue

        etp = classify_etp(href)
        if etp and _is_trade_url(href):
            out["etp_links"].append({"title": title, "url": href, "platform": etp, "source": "page_link"})
            continue

        host = urlparse(href).netloc
        if host and "zakupki.gov.ru" not in host:
            out["other_links"].append({"title": title, "url": href})

    return out


def _doc_kind(url: str) -> str:
    low = url.lower()
    for ext in ("docx", "doc", "xlsx", "xls", "pdf", "zip", "rar"):
        if f".{ext}" in low:
            return ext
    if "filestore" in low:
        return "filestore"
    return "file"


def _merge_lists(dst: List[dict], src: List[dict], key: str = "url") -> None:
    seen = {x[key] for x in dst}
    for item in src:
        if item[key] not in seen:
            dst.append(item)
            seen.add(item[key])


def discover_eis_sources(reg: str, entry_url: str, *, fetch_tabs: bool = True) -> Dict:
    """Return structured source links for one EIS notice."""
    result = {
        "reg_number": reg,
        "entry_url": entry_url,
        "notice_guid": "",
        "eis_pages": {},
        "etp_links": [],
        "document_links": [],
        "lot_links": [],
        "other_links": [],
        "notes": [],
    }

    try:
        html = fetch(entry_url, timeout=45)
    except Exception as exc:
        result["notes"].append(f"entry_fetch_failed: {exc}")
        return result

    result["notice_guid"] = _extract_guid(html)
    result["eis_pages"]["entry"] = entry_url
    result["eis_pages"].update(epz_urls(reg, result["notice_guid"]))

    scanned = _scan_page(html, entry_url)
    card_etp = _parse_card_platform(html)
    _merge_lists(result["etp_links"], card_etp)
    _merge_lists(result["document_links"], scanned["document_links"])
    _merge_lists(result["lot_links"], scanned["lot_links"])
    _merge_lists(result["other_links"], scanned["other_links"])

    epz_url = result["eis_pages"].get("eis_common_info_epz")
    if epz_url and epz_url != entry_url:
        try:
            epz_html = fetch(epz_url, timeout=45)
            _merge_lists(result["etp_links"], _parse_card_platform(epz_html))
            epz_scan = _scan_page(epz_html, epz_url)
            _merge_lists(result["etp_links"], epz_scan["etp_links"])
            _merge_lists(result["lot_links"], epz_scan["lot_links"])
        except Exception as exc:
            result["notes"].append(f"epz_common_fetch_failed:{exc}")

    pages_to_fetch = []
    if fetch_tabs:
        u = result["eis_pages"].get("eis_documents")
        if u:
            pages_to_fetch.append(("eis_documents", u))
        for tab in scanned["eis_tabs"]:
            if "documents.html" in tab["url"]:
                pages_to_fetch.append(("tab", tab["url"]))

    fetched = set()
    for _, url in pages_to_fetch:
        if url in fetched:
            continue
        fetched.add(url)
        try:
            sub_html = fetch(url, timeout=45)
        except Exception as exc:
            result["notes"].append(f"tab_fetch_failed:{url[:60]}: {exc}")
            continue
        sub = _scan_page(sub_html, url)
        _merge_lists(result["document_links"], sub["document_links"])
        _merge_lists(result["etp_links"], sub["etp_links"])

    platforms = sorted({x["platform"] for x in result["etp_links"]})
    result["etp_platforms"] = platforms
    primary = None
    for pref in ("roseltorg_atom", "fabrikant", "rts_tender", "sberbank_ast", "etpgpb", "tektorg", "lot_online"):
        primary = next((x for x in result["etp_links"] if x.get("platform") == pref), None)
        if primary:
            break
    if not primary:
        primary = next(
            (x for x in result["etp_links"] if "atom" in x.get("url", "").lower()),
            None,
        )
    if not primary:
        primary = next(
            (x for x in result["etp_links"] if x.get("source", "").startswith("eis_card")),
            None,
        )
    if not primary and result["etp_links"]:
        primary = result["etp_links"][0]
    result["primary_etp_url"] = primary["url"] if primary else ""
    result["primary_etp_platform"] = primary.get("platform", "") if primary else ""
    result["document_count"] = len(result["document_links"])
    if not result["document_links"]:
        result["notes"].append("documents_tab_empty")
    if not result["etp_links"]:
        result["notes"].append("etp_not_in_card")
    elif not result["document_links"]:
        result["notes"].append("etp_only_no_docs")
    return result


def _build_source_notes(sources: Dict) -> str:
    parts = []
    etp_url = sources.get("primary_etp_url") or ""
    etp_plat = sources.get("primary_etp_platform") or ""
    docs = sources.get("document_links") or []
    doc_page = (sources.get("eis_pages") or {}).get("eis_documents", "")
    extra = sources.get("notes") or []

    if etp_url:
        label = etp_plat or "etp"
        parts.append(f"ETP ({label}): {etp_url}")
    else:
        parts.append("ETP: не найден в карточке")

    if doc_page:
        parts.append(f"Документы ({len(docs)} файлов): {doc_page}")
    elif docs:
        parts.append(f"Документы: {len(docs)} файлов")
    else:
        parts.append("Документы: вложений нет")

    if etp_url and docs:
        parts.append("позиции: сначала ЭТП, иначе docx/xlsx из документов")
    elif etp_url:
        parts.append("позиции: только ЭТП")
    elif docs:
        parts.append("позиции: только документы (docx/xlsx/pdf)")
    else:
        parts.append("позиции: источников нет")

    for n in extra:
        if n not in ("documents_tab_empty", "etp_not_in_card", "etp_only_no_docs"):
            parts.append(n)
    return " | ".join(parts)


def sources_to_row_fields(sources: Dict) -> Dict[str, str]:
    """Flatten for spreadsheet: ETP + documents + notes."""
    docs = sources.get("document_links") or []
    pages = sources.get("eis_pages") or {}

    def join_docs(limit=10):
        if not docs:
            return ""
        return " | ".join(
            f"{d.get('title', '')[:50]} → {d['url']}" for d in docs[:limit]
        )

    return {
        "Platform URL": sources.get("primary_etp_url", ""),
        "EIS documents URL": pages.get("eis_documents", ""),
        "Document links": join_docs(10),
        "Source notes": _build_source_notes(sources),
    }
