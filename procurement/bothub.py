# -*- coding: utf-8 -*-
"""Bothub OpenAI-compatible classifier for procurement rows."""
from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.request
from typing import List, Tuple

from procurement.config import bothub_config
from procurement.reasoning_filter import classify

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

SYSTEM_PROMPT = """You filter Russian public procurement rows for nuclear power plant (AES) construction projects.
Keep rows that are supply of equipment/materials or construction-related procurement for a tracked AES object.
Reject: pure services, insurance, office supplies unrelated to NPP, monitoring/CP requests, PIR/design only,
training, IT support, rent, cancelled noise without supply.

Respond ONLY with JSON array. Each element:
{"idx": <int>, "verdict": "keep"|"reject", "object": "<best matching AES object name or empty>", "reason": "<short code>"}
Reason codes: relevant_supply, relevant_construction, exclusion, unknown_object, service_only, weak_link
"""


def _heuristic_batch(rows: List[dict]) -> List[dict]:
    out = []
    for i, row in enumerate(rows):
        objs = [x.strip() for x in str(row.get("Object", "")).split(";") if x.strip()]
        verdict, reason = classify(
            str(row.get("Description", "")),
            objs,
            str(row.get("Customer name", "")),
        )
        mapped = "keep" if verdict in ("keep", "review") else "reject"
        if mapped == "keep" and reason == "object matched, weak supply signal":
            reason = "relevant_supply"
        if mapped == "reject" and reason == "hard noise pattern":
            reason = "exclusion"
        out.append(
            {
                "idx": i,
                "verdict": mapped,
                "object": objs[0] if objs else "",
                "reason": reason if mapped == "reject" else "relevant_supply",
            }
        )
    return out


def _call_bothub(batch: List[dict], objects: List[str]) -> List[dict]:
    cfg = bothub_config()
    if not cfg["api_key"]:
        return _heuristic_batch(batch)

    payload_rows = []
    for i, row in enumerate(batch):
        payload_rows.append(
            {
                "idx": i,
                "object_hint": row.get("Object", ""),
                "description": str(row.get("Description", ""))[:1200],
                "customer": str(row.get("Customer name", ""))[:300],
                "item": str(row.get("Item", ""))[:200],
            }
        )
    user_content = (
        "Tracked AES objects:\n"
        + "\n".join(f"- {o}" for o in objects[:40])
        + "\n\nRows:\n"
        + json.dumps(payload_rows, ensure_ascii=False)
    )
    body = json.dumps(
        {
            "model": cfg["model"],
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0,
            "max_tokens": 2000,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    url = cfg["endpoint"] + "/chat/completions"
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": "Bearer " + cfg["api_key"],
            "Content-Type": "application/json",
        },
    )
    last_exc = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=120, context=CTX) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except (urllib.error.URLError, TimeoutError, ConnectionResetError, OSError) as exc:
            last_exc = exc
            if attempt + 1 >= 5:
                raise
            time.sleep(min(2 ** attempt, 16))
    else:
        raise last_exc  # type: ignore[misc]
    text = data["choices"][0]["message"]["content"]
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return _heuristic_batch(batch)
    return json.loads(m.group(0))


def classify_rows(
    rows: List[dict],
    objects: List[str],
    *,
    batch_size: int = 15,
    pause_sec: float = 0.5,
) -> Tuple[List[dict], List[dict]]:
    kept: List[dict] = []
    rejected: List[dict] = []
    total_batches = (len(rows) + batch_size - 1) // batch_size
    for batch_no, start in enumerate(range(0, len(rows), batch_size), start=1):
        chunk = rows[start : start + batch_size]
        try:
            verdicts = _call_bothub(chunk, objects)
        except (
            urllib.error.URLError,
            TimeoutError,
            ConnectionResetError,
            OSError,
            KeyError,
            json.JSONDecodeError,
        ) as exc:
            print(f"  Bothub API error batch {batch_no}, fallback to heuristic:", exc)
            verdicts = _heuristic_batch(chunk)
        by_idx = {v["idx"]: v for v in verdicts}
        for i, row in enumerate(chunk):
            v = by_idx.get(i, {"verdict": "keep", "object": row.get("Object", ""), "reason": "relevant_supply"})
            row = dict(row)
            if v.get("object"):
                row["Object"] = v["object"]
            if v.get("verdict") == "keep":
                kept.append(row)
            else:
                row["_filter_reason"] = v.get("reason", "exclusion")
                rejected.append(row)
        if batch_no == 1 or batch_no % 10 == 0 or batch_no == total_batches:
            print(f"  batch {batch_no}/{total_batches}, kept {len(kept)}, rejected {len(rejected)}")
        if start + batch_size < len(rows):
            time.sleep(pause_sec)
    return kept, rejected
