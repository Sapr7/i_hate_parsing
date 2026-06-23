# -*- coding: utf-8 -*-
import re
import time
from typing import Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

LABEL_MAP = {
    "номер закупки": "rosatom_number",
    "статус": "status",
    "начальная (максимальная) цена договора в рублях": "price_rub",
    "ссылка на закупку на еис": "eis_url",
    "ссылка на закупку на этп": "etp_url",
    "наименование организации": "organizer",
    "предмет закупки": "subject",
    "дата публикации извещения": "publish_date",
    "является мониторингом цен": "is_price_monitoring",
}


def _make_driver(headless: bool = True):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1400,900")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    return webdriver.Chrome(options=opts)


def parse_label_fields(html: str) -> Dict[str, str]:
    soup = BeautifulSoup(html, "lxml")
    out: Dict[str, str] = {}
    title = soup.select_one("div.text[style*='font-size: 32px']")
    if title:
        out["page_title"] = title.get_text(" ", strip=True)

    blocks = soup.select("div.af-core-items.grid-column.columns")
    for block in blocks:
        labels = block.select("span.af-item__title")
        for lab in labels:
            label = lab.get_text(" ", strip=True)
            if not label:
                continue
            parent = lab.find_parent("div", class_="af-item")
            if not parent:
                continue
            row = parent.find_parent("div", class_=re.compile("grid-column|grid-row"))
            if not row:
                continue
            value = ""
            for sib in row.select("div.af-item"):
                if sib is parent:
                    continue
                link = sib.select_one("a.link[href]")
                if link:
                    value = link.get("href", "").strip()
                    break
                text_el = sib.select_one("div.af-core-label div.text")
                if text_el:
                    value = text_el.get_text(" ", strip=True)
                    break
            key = LABEL_MAP.get(label.lower())
            if key and value:
                out[key] = value
    return out


def parse_stages(html: str) -> Dict[str, str]:
    soup = BeautifulSoup(html, "lxml")
    out = {"application_start": "", "results_date": ""}
    for row in soup.select("div.af-item, tr"):
        text = row.get_text(" ", strip=True)
        low = text.lower()
        if "начал" in low and "прием" in low and "заяв" in low:
            m = re.search(r"\d{2}\.\d{2}\.\d{4}", text)
            if m:
                out["application_start"] = m.group(0)
        if "подвед" in low and "итог" in low:
            m = re.search(r"\d{2}\.\d{2}\.\d{4}", text)
            if m:
                out["results_date"] = m.group(0)
    return out


def parse_procurement(url: str, headless: bool = True, wait_sec: int = 8) -> Dict[str, str]:
    driver = _make_driver(headless=headless)
    try:
        return _parse_with_driver(driver, url, wait_sec=wait_sec)
    finally:
        driver.quit()


def _parse_with_driver(driver, url: str, wait_sec: int = 8) -> Dict[str, str]:
    driver.set_page_load_timeout(90)
    driver.get(url)
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "span.af-item__title"))
    )
    time.sleep(wait_sec)
    data = parse_label_fields(driver.page_source)

    tabs = driver.find_elements(By.CSS_SELECTOR, "a.tabs-item")
    for tab in tabs:
        if "Этапы закупки" in tab.text:
            tab.click()
            time.sleep(3)
            data.update(parse_stages(driver.page_source))
            break
    data["source_url"] = url
    return data


def parse_procurements_batch(
    urls: List[str],
    headless: bool = True,
    wait_sec: int = 6,
) -> List[Dict[str, str]]:
    """Parse many Rosatom cards reusing one browser session."""
    if not urls:
        return []
    driver = _make_driver(headless=headless)
    results: List[Dict[str, str]] = []
    try:
        driver.set_page_load_timeout(90)
        for i, url in enumerate(urls, 1):
            try:
                results.append(_parse_with_driver(driver, url, wait_sec=wait_sec))
            except Exception as err:
                results.append({"source_url": url, "error": str(err)})
            if i % 10 == 0:
                print(f"    Rosatom cards parsed: {i}/{len(urls)}")
    finally:
        driver.quit()
    return results


def discover_procurement_urls(list_url: str, headless: bool = True, limit: int = 20) -> List[str]:
    """Best-effort: collect obj_id links from a Rosatom list page."""
    driver = _make_driver(headless=headless)
    urls: List[str] = []
    try:
        driver.set_page_load_timeout(90)
        driver.get(list_url)
        time.sleep(10)
        html = driver.page_source
        if "Техническая поддержка" in driver.title:
            return []
        for m in re.finditer(r"obj_id=(\d+)", html):
            oid = m.group(1)
            u = f"https://zakupki.rosatom.ru/{oid}?link=procurements&obj_id={oid}"
            if u not in urls:
                urls.append(u)
            if len(urls) >= limit:
                break
    finally:
        driver.quit()
    return urls
