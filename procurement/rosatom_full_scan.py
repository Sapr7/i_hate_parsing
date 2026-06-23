# -*- coding: utf-8 -*-
import json, re, sys, time
from pathlib import Path
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from procurement.rosatom import _make_driver
from procurement.matching import match_any_object
from procurement.objects import load_objects

ROSATOM_LISTS = [
    ("completed", "https://zakupki.rosatom.ru/?link=completed_procurements"),
    ("archive", "https://zakupki.rosatom.ru/?link=procurements_archive"),
    ("published", "https://zakupki.rosatom.ru/?link=procurements"),
    ("cancelled", "https://zakupki.rosatom.ru/?link=cancelled_procurements"),
]
YEAR_FROM, YEAR_TO = 2020, 2026
MAX_PAGES = 400
EMPTY_STOP = 5

def log(msg):
    print(msg, flush=True)

def rosatom_number_to_id(number):
    return re.sub(r"\D", "", number or "")

def parse_year(date_str):
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", date_str or "")
    return int(m.group(3)) if m else None

def parse_list_page(html, list_source):
    soup = BeautifulSoup(html, "lxml")
    rows = []
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
        publish = date_td.get_text(" ", strip=True) if date_td else ""
        rows.append({
            "rosatom_number": number,
            "rosatom_id": rid,
            "url": f"https://zakupki.rosatom.ru/{rid}?link=procurements_archive&obj_id={rid}",
            "subject": subj_td.get_text(" ", strip=True) if subj_td else "",
            "organizer": org_td.get_text(" ", strip=True) if org_td else "",
            "status": stat_td.get_text(" ", strip=True) if stat_td else "",
            "price_rub": price_td.get_text(" ", strip=True) if price_td else "",
            "publish_date": publish,
            "year": parse_year(publish),
            "list_source": list_source,
        })
    return rows

def paginator_max(html):
    nums = [int(s.get_text(strip=True)) for s in BeautifulSoup(html, "lxml").select("div.af-paginator__item span") if s.get_text(strip=True).isdigit()]
    return max(nums) if nums else 1

def click_next(driver):
    for sel in ["button .af-paginator__next", ".af-paginator__next"]:
        for el in driver.find_elements(By.CSS_SELECTOR, sel):
            try:
                btn = el.find_element(By.XPATH, "./ancestor::button")
            except Exception:
                btn = el
            if btn.is_displayed():
                driver.execute_script("arguments[0].click();", btn)
                return True
    return False

def crawl_list(driver, name, url, wait_sec=7):
    log(f"  [{name}] open...")
    driver.get(url)
    time.sleep(wait_sec)
    if "Техническая поддержка" in (driver.title or ""):
        log(f"  [{name}] WAF")
        return {}, 0
    pages_hint = paginator_max(driver.page_source)
    found = {}
    page = 0
    empty_streak = 0
    while page < MAX_PAGES:
        page += 1
        rows = parse_list_page(driver.page_source, url)
        in_range = 0
        years = [r["year"] for r in rows if r.get("year")]
        for row in rows:
            y = row.get("year")
            if y and YEAR_FROM <= y <= YEAR_TO:
                found.setdefault(row["rosatom_id"], row)
                in_range += 1
        if in_range == 0:
            empty_streak += 1
        else:
            empty_streak = 0
        if page == 1:
            log(f"  [{name}] total pages~{pages_hint}, page1={len(rows)}, in_range={in_range}")
        elif page % 20 == 0:
            log(f"  [{name}] page {page}/{pages_hint}, unique={len(found)}")
        if years and min(years) < YEAR_FROM:
            log(f"  [{name}] reached year<{YEAR_FROM}, stop")
            break
        if empty_streak >= EMPTY_STOP:
            log(f"  [{name}] {EMPTY_STOP} empty pages, stop")
            break
        if not click_next(driver):
            break
        time.sleep(wait_sec)
    log(f"  [{name}] DONE pages={page}, unique={len(found)}")
    return found, page

def main():
    objects = load_objects("2 (3).xlsx")
    log(f"Rosatom full crawl {YEAR_FROM}-{YEAR_TO}, max {MAX_PAGES} pages/list")
    log("=" * 55)
    driver = _make_driver(headless=True)
    all_found = {}
    per_list = {}
    pages_total = 0
    try:
        driver.set_page_load_timeout(90)
        for name, url in ROSATOM_LISTS:
            rows, pages = crawl_list(driver, name, url)
            per_list[name] = len(rows)
            pages_total += pages
            all_found.update(rows)
            Path("output").mkdir(exist_ok=True)
            Path("output/rosatom_full_progress.json").write_text(json.dumps({"per_list": per_list, "total": len(all_found), "pages": pages_total}, ensure_ascii=False), encoding="utf-8")
    finally:
        driver.quit()
    aes = {}
    for rid, row in all_found.items():
        matched = match_any_object(row.get("subject", ""), objects)
        if not matched:
            continue
        item = dict(row)
        item["matched_objects"] = matched
        item["matched_object"] = "; ".join(matched[:2])
        item["search_query"] = "rosatom_full_crawl"
        aes[rid] = item
    log("=" * 55)
    log("RESULTS")
    for name, n in per_list.items():
        log(f"  {name}: {n}")
    log(f"  TOTAL unique {YEAR_FROM}-{YEAR_TO}: {len(all_found)}")
    log(f"  AES loose filter: {len(aes)}")
    log(f"  Pages crawled: {pages_total}")
    aes_rows = list(aes.values())
    out = {
        "stats": {"total": len(all_found), "aes": len(aes), "per_list": per_list, "pages": pages_total},
        "by_id": aes,
    }
    Path("output/rosatom_full_aes.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    if aes_rows:
        import pandas as pd
        pd.DataFrame(aes_rows).to_excel("output/rosatom_full_hits.xlsx", index=False)
    Path("output/rosatom_full_scan.json").write_text(
        json.dumps({"stats": out["stats"]}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log("Saved output/rosatom_full_hits.xlsx")
    log("Saved output/rosatom_full_aes.json")

if __name__ == "__main__":
    main()