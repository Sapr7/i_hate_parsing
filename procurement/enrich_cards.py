# -*- coding: utf-8 -*-
"""Enrich kept rows by parsing EIS / Rosatom cards (after Bothub filter)."""
from __future__ import annotations

import re
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

from procurement.eis_card import parse_eis_card
from procurement.enrich import extract_lot_number, rosatom_to_rows
from procurement.rosatom import parse_procurements_batch

EIS_REG_RE = re.compile(r"regNum(?:ber)?=(\d+)", re.I)
EIS_SEARCH_RE = re.compile(r"searchString=(\d+)", re.I)


def eis_reg_from_url(url: str) -> str:
    for pattern in (EIS_REG_RE, EIS_SEARCH_RE):
        m = pattern.search(url or "")
        if m:
            return m.group(1)
    return ""


def _load_json_cache(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_json_cache(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _merge_fields(row: dict, patch: dict) -> dict:
    out = dict(row)
    mapping = {
        "initial_price": "Initial price",
        "publish_date": "Publish date",
        "deadline_date": "Deadline date",
        "contract_execution_date": "Contract Execution Date",
        "customer_name": "Customer name",
        "supplier_number": "Supplier number",
        "eis_url": "EIS URL",
        "platform_url": "Platform URL",
    }
    for src, dst in mapping.items():
        val = patch.get(src, "")
        if val and not str(out.get(dst, "") or "").strip():
            out[dst] = val
    return out


def _apply_rosatom_to_eis(
    eis_row: dict,
    ros_row: dict,
    base_patch: dict,
    header: dict,
    card_rows: List[dict],
) -> List[dict]:
    merged = dict(eis_row)
    ros_url = str(ros_row.get("Rosatom URL", "") or "").strip()
    if ros_url:
        merged["Rosatom URL"] = ros_url
    merged = _merge_fields(merged, base_patch)

    subj = header.get("subject") or header.get("page_title", "")
    if len(card_rows) == 1 and not card_rows[0].get("Quantity"):
        if not str(merged.get("Description", "") or "").strip():
            merged["Description"] = subj
        return [merged]

    out: List[dict] = []
    eis_notice = str(eis_row.get("Notice number", "") or "").strip()
    for cr in card_rows:
        row = _merge_fields({**merged, **cr}, base_patch)
        if ros_url:
            row["Rosatom URL"] = ros_url
        if eis_notice:
            row["Notice number"] = eis_notice
        out.append(row)
    return out


def enrich_kept_rows(
    rows: List[dict],
    *,
    headless: bool = True,
    wait_sec: int = 5,
    pause_sec: float = 0.3,
    overlaps_out: Optional[List[dict]] = None,
    cache_dir: str = "output",
) -> List[dict]:
    """Enrich rows; overlap pairs are appended to overlaps_out when provided."""
    enriched: List[dict] = []
    seen_eis: Set[str] = set()
    rosatom_urls: List[str] = []
    cache_root = Path(cache_dir)
    eis_cache_path = cache_root / "eis_card_cache.json"
    rosatom_cache_path = cache_root / "rosatom_headers_cache.json"
    eis_cache = _load_json_cache(eis_cache_path)
    rosatom_cache = _load_json_cache(rosatom_cache_path)
    eis_hits = 0

    for row in rows:
        eis_url = str(row.get("EIS URL", "") or "").strip()
        ros_url = str(row.get("Rosatom URL", "") or "").strip()
        if eis_url and eis_url != "nan":
            reg = eis_reg_from_url(eis_url)
            if reg:
                seen_eis.add(reg)
            if reg and reg in eis_cache:
                patch = eis_cache[reg]
                eis_hits += 1
            else:
                patch = parse_eis_card(eis_url)
                if reg:
                    eis_cache[reg] = patch
                    _save_json_cache(eis_cache_path, eis_cache)
                if pause_sec:
                    time.sleep(pause_sec)
            enriched.append(_merge_fields(row, patch))
        elif ros_url and ros_url != "nan":
            rosatom_urls.append(ros_url)
            enriched.append(dict(row))
        else:
            enriched.append(dict(row))

    overlaps: List[dict] = []
    if not rosatom_urls:
        if overlaps_out is not None:
            overlaps_out.extend(overlaps)
        return enriched

    if eis_hits:
        print(f"  EIS cache hits: {eis_hits}/{len(eis_cache)} cached regs")

    missing_ros = [u for u in rosatom_urls if u not in rosatom_cache]
    if missing_ros:
        print(f"  enriching {len(missing_ros)} Rosatom cards ({len(rosatom_urls) - len(missing_ros)} cached)...")
        fresh = parse_procurements_batch(missing_ros, headless=headless, wait_sec=wait_sec)
        for url, header in zip(missing_ros, fresh):
            rosatom_cache[url] = header
        _save_json_cache(rosatom_cache_path, rosatom_cache)
    else:
        print(f"  Rosatom cards: all {len(rosatom_urls)} from cache")
    headers = [rosatom_cache.get(u, {"error": "missing"}) for u in rosatom_urls]
    out: List[dict] = []
    eis_out_idx: Dict[str, int] = {}
    ros_out_i = 0
    eis_regs_out: Set[str] = set(seen_eis)

    for row in enriched:
        ros_url = str(row.get("Rosatom URL", "") or "").strip()
        if not ros_url or ros_url == "nan":
            reg = eis_reg_from_url(str(row.get("EIS URL", "") or ""))
            out.append(row)
            if reg:
                eis_out_idx[reg] = len(out) - 1
                eis_regs_out.add(reg)
            continue

        header = headers[ros_out_i] if ros_out_i < len(headers) else {"error": "missing"}
        ros_out_i += 1
        if header.get("error"):
            out.append(row)
            continue

        eis_link = str(header.get("eis_url", "") or "").strip()
        eis_reg = eis_reg_from_url(eis_link)
        if eis_reg and eis_reg in eis_regs_out:
            idx = eis_out_idx.get(eis_reg)
            if idx is not None:
                mobj = str(row.get("Object", "") or "").strip()
                matched = [mobj] if mobj else []
                subj = header.get("subject") or header.get("page_title", "")
                lot = extract_lot_number(subj) or extract_lot_number(str(row.get("Description", "")))
                base_patch = {
                    "initial_price": header.get("price_rub", ""),
                    "publish_date": header.get("publish_date", ""),
                    "deadline_date": header.get("application_start", ""),
                    "contract_execution_date": header.get("results_date", ""),
                    "customer_name": header.get("organizer", "") or row.get("Customer name", ""),
                    "supplier_number": lot,
                    "eis_url": eis_link or str(out[idx].get("EIS URL", "") or ""),
                    "platform_url": header.get("etp_url", ""),
                }
                card_rows = rosatom_to_rows(header, matched)
                merged_rows = _apply_rosatom_to_eis(out[idx], row, base_patch, header, card_rows)
                out[idx : idx + 1] = merged_rows
                overlaps.append(
                    {
                        "eis_reg": eis_reg,
                        "eis_notice": str(out[idx].get("Notice number", "") or ""),
                        "rosatom_notice": header.get("rosatom_number", "") or row.get("Notice number", ""),
                        "eis_url": str(out[idx].get("EIS URL", "") or eis_link),
                        "rosatom_url": ros_url,
                        "platform_url": header.get("etp_url", ""),
                        "action": "merged_into_eis_row",
                    }
                )
                continue

        if eis_reg:
            eis_regs_out.add(eis_reg)

        mobj = str(row.get("Object", "") or "").strip()
        matched = [mobj] if mobj else []
        subj = header.get("subject") or header.get("page_title", "")
        lot = extract_lot_number(subj) or extract_lot_number(str(row.get("Description", "")))
        base_patch = {
            "initial_price": header.get("price_rub", ""),
            "publish_date": header.get("publish_date", ""),
            "deadline_date": header.get("application_start", ""),
            "contract_execution_date": header.get("results_date", ""),
            "customer_name": header.get("organizer", "") or row.get("Customer name", ""),
            "supplier_number": lot,
            "eis_url": eis_link,
            "platform_url": header.get("etp_url", ""),
        }
        card_rows = rosatom_to_rows(header, matched)
        if len(card_rows) == 1 and not card_rows[0].get("Quantity"):
            merged = _merge_fields(row, base_patch)
            if not str(merged.get("Description", "") or "").strip():
                merged["Description"] = subj
            out.append(merged)
        else:
            for cr in card_rows:
                out.append(_merge_fields({**row, **cr}, base_patch))

    eis_in = sum(
        1
        for r in rows
        if str(r.get("EIS URL", "") or "").strip() not in ("", "nan")
    )
    ros_in = sum(
        1
        for r in rows
        if str(r.get("Rosatom URL", "") or "").strip() not in ("", "nan")
    )
    if overlaps:
        print(
            f"  merged {len(overlaps)} Rosatom↔EIS overlaps "
            f"({ros_in} rosatom in → {len(out) - eis_in} rosatom-only rows out)"
        )

    if overlaps_out is not None:
        overlaps_out.extend(overlaps)
    return out
