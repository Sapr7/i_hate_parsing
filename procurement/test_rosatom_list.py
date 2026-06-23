import re
import time
from bs4 import BeautifulSoup
from procurement.rosatom import _make_driver

def number_to_id(num):
    return re.sub(r"\D", "", num)

def parse_list_html(html, list_source):
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for tr in soup.select("tr.af-table-body-tr"):
        num_td = tr.select_one('td[id$="-Номер"]')
        subj_td = tr.select_one('td[id$="-ПравоЗаключенияДоговораНа"]')
        org_td = tr.select_one('td[id$="-ОрганизаторЗакупки"]')
        stat_td = tr.select_one('td[id$="-РасширенныйСтатус"]')
        if not num_td:
            continue
        num = num_td.get_text(" ", strip=True)
        rid = number_to_id(num)
        if len(rid) < 10:
            continue
        rows.append({
            "rosatom_number": num,
            "rosatom_id": rid,
            "url": f"https://zakupki.rosatom.ru/{rid}?link=procurements_archive&obj_id={rid}",
            "subject": subj_td.get_text(" ", strip=True) if subj_td else "",
            "organizer": org_td.get_text(" ", strip=True) if org_td else "",
            "status": stat_td.get_text(" ", strip=True) if stat_td else "",
            "list_source": list_source,
        })
    return rows

driver = _make_driver(headless=True)
try:
    url = "https://zakupki.rosatom.ru/?link=procurements_archive"
    driver.get(url)
    time.sleep(12)
    rows = parse_list_html(driver.page_source, url)
    print("rows on page1", len(rows))
    if rows:
        print("sample", rows[0]["rosatom_number"], rows[0]["url"])
        print("paks in list", any("221129/1065/696" == r["rosatom_number"] for r in rows))
finally:
    driver.quit()