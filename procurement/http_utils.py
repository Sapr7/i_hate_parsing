# -*- coding: utf-8 -*-
import ssl
import urllib.request
from typing import Optional

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def fetch_bytes(url: str, timeout: int = 30, referer: Optional[str] = None) -> bytes:
    headers = {"User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.9"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
        return resp.read()


def decode_html(raw: bytes) -> str:
    for enc in ("utf-8", "cp1251", "windows-1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")
