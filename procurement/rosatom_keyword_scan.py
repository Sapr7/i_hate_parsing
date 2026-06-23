# -*- coding: utf-8 -*-
"""Rosatom search by AES object keywords (2020-2026)."""
import json, re, time
from pathlib import Path
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from procurement.rosatom import _make_driver
from procurement.matching import object_tokens
from procurement.objects import load_objects

ARCHIVE_URL = "https://zakupki.rosatom.ru/?link=procurements_archive"
YEAR_FROM, YEAR_TO = 2020, 2026
MAX_PAGES_PER_QUERY = 30
EMPTY_STOP = 3

def log(msg):
    print(msg, flush=True)

def rosatom_number_to_id(number):
    return re.sub(r"\D", "", number or "")

def parse_year(date_str):
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", date_str or "")
    return int(m.group(3)) if m else None

def parse_list_page(html, query, object_name):
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
        date_td = tr.select_one('td[id$="-Дата"]')
        publish = date_td.get_text(" ", strip=True) if date_td else ""
        y = parse_year(publish)
        if y and (y < YEAR_FROM or y > YEAR_TO):
            continue
        rows.append({
            "rosatom_number": number,
            "rosatom_id": rid,
            "url": f"https://zakupki.rosatom.ru/{rid}?link=procurements_archive&obj_id={rid}",
            "subject": subj_td.get_text(" ", strip=True) if subj_td else "",
            "organizer": org_td.get_text(" ", strip=True) if org_td else "",
            "status": stat_td.get_text(" ", strip=True) if stat_td else "",
            "publish_date": publish,
            "year": y,
            "search_query": query,
            "matched_object": object_name,
        })
    return rows

def paginator_total(html):
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

def find_search_input(driver):
    for inp in driver.find_elements(By.CSS_SELECTOR, "input[type='text']"):
        try:
            parent = inp.find_element(By.XPATH, "./ancestor::div[contains(@class,'af-input')]")
            if "Поиск" in parent.text:
                return inp
        except Exception:
            pass
    inputs = driver.find_elements(By.CSS_SELECTOR, "div.af-input__input input")
    return inputs[0] if inputs else None

def run_search(driver, query, object_name, wait_sec=6):
    driver.get(ARCHIVE_URL)
    time.sleep(wait_sec)
    inp = find_search_input(driver)
    if not inp:
        log(f"    ! no search box for '{query}'")
        return []
    inp.clear()
    inp.send_keys(query)
    time.sleep(0.5)
    inp.send_keys(Keys.RETURN)
    time.sleep(wait_sec)
    found = []
    page = 0
    empty_streak = 0
    pages_hint = paginator_total(driver.page_source)
    while page < MAX_PAGES_PER_QUERY:
        page += 1
        rows = parse_list_page(driver.page_source, query, object_name)
        if not rows:
            empty_streak += 1
        else:
            empty_streak = 0
            found.extend(rows)
        if page == 1:
            log(f"    q='{query}' pages~{pages_hint} page1={len(rows)}")
        years = [r["year"] for r in rows if r.get("year")]
        if years and min(years) < YEAR_FROM:
            break
        if empty_streak >= EMPTY_STOP:
            break
        if not click_next(driver):
            break
        time.sleep(wait_sec)
    log(f"    q='{query}' -> {len(found)} rows ({page} pages)")
    return found

def search_queries_for_object(name):
    qs = []
    if "«" in name and "»" in name:
        qs.append(name.split("«", 1)[1].split("»", 1)[0].strip())
    qs.append(name)
    for tok in object_tokens(name)[1:4]:
        if len(tok) >= 4 and tok not in qs:
            qs.append(tok)
    seen = set()
    out = []
    for q in qs:
        k = q.lower()
        if k not in seen:
            seen.add(k)
            out.append(q)
    return out[:3]

def main():
    objects = load_objects("2 (3).xlsx")
    log(f"Rosatom KEYWORD search {YEAR_FROM}-{YEAR_TO}, objects={len(objects)}")
    log("=" * 55)
    driver = _make_driver(headless=True)
    by_id = {}
    per_object = {}
    per_query = []
    try:
        driver.set_page_load_timeout(90)
        for obj in objects:
            log(f"[{obj}]")
            obj_ids = set()
            for q in search_queries_for_object(obj):
                rows = run_search(driver, q, obj)
                per_query.append({"object": obj, "query": q, "rows": len(rows)})
                for row in rows:
                    rid = row["rosatom_id"]
                    if rid not in by_id:
                        by_id[rid] = row
                    else:
                        prev = by_id[rid].get("matched_object", "")
                        if obj not in prev:
                            by_id[rid]["matched_object"] = (prev + "; " + obj).strip("; ")
                    obj_ids.add(rid)
                time.sleep(1)
            per_object[obj] = len(obj_ids)
            log(f"  object unique: {len(obj_ids)}")
            Path("output").mkdir(exist_ok=True)
            Path("output/rosatom_keyword_progress.json").write_text(
                json.dumps({"total": len(by_id), "per_object": per_object, "by_id": by_id}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            if by_id:
                import pandas as pd
                pd.DataFrame(list(by_id.values())).to_excel("output/rosatom_keyword_hits.xlsx", index=False)
    finally:
        driver.quit()
    log("=" * 55)
    log("KEYWORD SEARCH RESULTS")
    log(f"  TOTAL unique {YEAR_FROM}-{YEAR_TO}: {len(by_id)}")
    for obj, n in sorted(per_object.items(), key=lambda x: -x[1])[:15]:
        if n:
            log(f"  {n:4d}  {obj}")
    out = {
        "stats": {"total": len(by_id), "per_object": per_object, "queries": per_query},
        "sample": list(by_id.values())[:5],
    }
    Path("output/rosatom_keyword_scan.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    rows_export = list(by_id.values())
    if rows_export:
        import pandas as pd
        pd.DataFrame(rows_export).to_excel("output/rosatom_keyword_hits.xlsx", index=False)
    log("Saved output/rosatom_keyword_scan.json")
    log("Saved output/rosatom_keyword_hits.xlsx")

if __name__ == "__main__":
    main()