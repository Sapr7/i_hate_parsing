# -*- coding: utf-8 -*-
import json, re, time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from procurement.eis_client import object_search_queries, scan_customer_inn, scan_query_loose
from procurement.matching import match_any_object
from procurement.objects import load_customer_inns, load_objects
from procurement.rosatom_discover import discover_rosatom_rows

DATE_FROM_YEAR, DATE_TO_YEAR = 2020, 2026

@dataclass
class DiscoveryResult:
    objects: List[str] = field(default_factory=list)
    eis_by_reg: Dict[str, dict] = field(default_factory=dict)
    rosatom_by_id: Dict[str, dict] = field(default_factory=dict)
    rosatom_aes_filtered: Dict[str, dict] = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    def save(self, path: Path):
        payload = {"objects": self.objects, "eis_by_reg": self.eis_by_reg, "rosatom_by_id": self.rosatom_by_id, "rosatom_aes_filtered": self.rosatom_aes_filtered, "stats": self.stats}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    @classmethod
    def load(cls, path: Path):
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(objects=data.get("objects",[]), eis_by_reg=data.get("eis_by_reg",{}), rosatom_by_id=data.get("rosatom_by_id",{}), rosatom_aes_filtered=data.get("rosatom_aes_filtered",{}), stats=data.get("stats",{}))

def _year(d):
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", d or "")
    return int(m.group(3)) if m else None

def _serialize_eis(by_reg):
    out = {}
    for reg, item in by_reg.items():
        out[reg] = {**{k:v for k,v in item.items() if k not in ("matched_objects","queries")}, "matched_objects": sorted(item.get("matched_objects",[])), "queries": sorted(item.get("queries",[]))}
    return out

def discover_all(xlsx="2 (3).xlsx", skip_customer_inn=False, rosatom_list_pages=20, headless=True, max_eis=0, max_rosatom=0):
    objects = load_objects(xlsx)
    by_reg = {}
    print("\n" + "="*60)
    print("STAGE 1: DISCOVERY (counts before detail parse)")
    print("="*60)
    print("AES objects:", len(objects))
    print("\n[1/2] EIS zakupki.gov.ru ...")
    t0 = time.time()
    for i, name in enumerate(objects, 1):
        for q in object_search_queries(name):
            try: scan_query_loose(q, name, by_reg)
            except Exception as e: print("  error", name, q, e)
            time.sleep(0.2)
        if max_eis and len(by_reg) >= max_eis: break
        if i % 5 == 0: print("  objects", i, "/", len(objects), "unique", len(by_reg))
    eis_object_n = len(by_reg)
    inn_added = 0
    if not skip_customer_inn:
        print("\n[1/2] EIS by customer INN ...")
        for org, inn in load_customer_inns(xlsx):
            before = len(by_reg)
            try: scan_customer_inn(inn, org, objects, by_reg)
            except Exception as e: print("  error INN", inn, e)
            inn_added += len(by_reg)-before
            time.sleep(0.25)
            if max_eis and len(by_reg) >= max_eis: break
    if max_eis: by_reg = dict(list(by_reg.items())[:max_eis])
    print("\n  EIS total:", len(by_reg), "in", int(time.time()-t0), "sec")
    print("    object-search:", eis_object_n, " inn-added:", inn_added)
    print("\n[2/2] Rosatom zakupki.rosatom.ru lists (Selenium)...")
    t1 = time.time()
    rosatom_all = discover_rosatom_rows(headless=headless, max_pages_per_list=rosatom_list_pages)
    rosatom_aes = {}
    for rid, row in rosatom_all.items():
        y = _year(row.get("publish_date",""))
        if y and (y < DATE_FROM_YEAR or y > DATE_TO_YEAR): continue
        matched = match_any_object(row.get("subject",""), objects)
        if matched:
            r = dict(row); r["matched_objects"] = matched; rosatom_aes[rid] = r
    if max_rosatom: rosatom_aes = dict(list(rosatom_aes.items())[:max_rosatom])
    print("\n  Rosatom all lists:", len(rosatom_all), "in", int(time.time()-t1), "sec")
    print("  Rosatom AES-filtered", DATE_FROM_YEAR, "-", DATE_TO_YEAR, ":", len(rosatom_aes))
    stats = {"objects_count": len(objects), "eis_total": len(by_reg), "eis_from_object_search": eis_object_n, "eis_from_customer_inn_added": inn_added, "rosatom_list_total": len(rosatom_all), "rosatom_aes_filtered": len(rosatom_aes), "fabrikant_cards_estimate": len(rosatom_aes)}
    print("\n" + "-"*60)
    print("SUMMARY BEFORE DETAIL PARSING")
    print("-"*60)
    print("  EIS (goszakupki.gov.ru):      ", stats["eis_total"])
    print("  Rosatom (all list rows):      ", stats["rosatom_list_total"])
    print("  Rosatom (AES relevant):       ", stats["rosatom_aes_filtered"])
    print("  Fabrikant cards (estimate):   ", stats["fabrikant_cards_estimate"])
    print("-"*60)
    return DiscoveryResult(objects=objects, eis_by_reg=_serialize_eis(by_reg), rosatom_by_id=rosatom_all, rosatom_aes_filtered=rosatom_aes, stats=stats)

def print_discovery_banner(result):
    print("\n>>> Starting detail parse + Bothub filter...\n")