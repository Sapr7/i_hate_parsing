#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, ssl, urllib.error, urllib.request
from procurement.config import bothub_config
CTX = ssl.create_default_context(); CTX.check_hostname=False; CTX.verify_mode=ssl.CERT_NONE
PROBES = [
    ("GET", "https://bothub.chat/api/v2/openai/v1/models"),
    ("GET", "https://openai.bothub.chat/v1/models"),
    ("GET", "https://bothub.chat/api/v2/user/me"),
    ("GET", "https://bothub.chat/api/v2/user/balance"),
]
def probe(url, key):
    req = urllib.request.Request(url, headers={"Accept":"application/json","Authorization":"Bearer "+key})
    try:
        with urllib.request.urlopen(req, timeout=30, context=CTX) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body[:400]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")[:400]
    except Exception as e:
        return None, str(e)[:400]
def mini_chat(endpoint, key, model):
    url = endpoint.rstrip("/") + "/chat/completions"
    payload = json.dumps({"model": model, "messages":[{"role":"user","content":"ping"}], "max_tokens":5}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60, context=CTX) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return resp.status, json.dumps(data.get("usage") or {})
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")[:400]
    except Exception as e:
        return None, str(e)[:400]
cfg = bothub_config()
print("endpoint:", cfg["endpoint"])
print("model:", cfg["model"])
print("key configured:", bool(cfg["api_key"]))
if not cfg["api_key"]:
    raise SystemExit(1)
print("\n--- probes ---")
for _, url in PROBES:
    st, body = probe(url, cfg["api_key"])
    print(f"{st or 'ERR'} {url}\n  {body}\n")
print("--- mini chat ---")
st, body = mini_chat(cfg["endpoint"], cfg["api_key"], cfg["model"])
print(f"{st or 'ERR'} chat/completions\n  {body}")