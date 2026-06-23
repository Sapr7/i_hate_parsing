# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

import pandas as pd

from procurement.matching import EXTRA_OBJECTS, normalize_text


def load_objects(xlsx: Path | str = "2 (3).xlsx") -> List[str]:
    path = Path(xlsx)
    obj = pd.read_excel(path, sheet_name="объекты", header=1).fillna("")
    names = []
    for val in obj.iloc[:, 1]:
        name = str(val).strip()
        if not name:
            continue
        low = name.lower()
        if "аэс" in low or "асмм" in low:
            names.append(name)
    for extra in EXTRA_OBJECTS:
        if "Ostrovets" in extra:
            continue
        if extra not in names:
            names.append(extra)
    seen = set()
    uniq = []
    for n in names:
        key = normalize_text(n)
        if key not in seen:
            seen.add(key)
            uniq.append(n)
    return uniq


def load_customer_inns(xlsx: Path | str = "2 (3).xlsx") -> List[Tuple[str, str]]:
    path = Path(xlsx)
    df = pd.read_excel(path, sheet_name="дочки росатома", header=1).fillna("")
    rows: List[Tuple[str, str]] = []
    keywords = (
        "атомстрой", "никимт", "монтаж", "атомкомплект", "атомэнергопроект",
        "атомстройэкспорт", "энергоспецмонтаж", "атомэнергомаш", "асэ",
    )
    for _, row in df.iterrows():
        org = str(row.iloc[1]).strip()
        inn = re.sub(r"\D", "", str(row.iloc[2]))
        if not org or not inn:
            continue
        if any(k in org.lower() for k in keywords):
            rows.append((org, inn))
    # Known customer from Belarus NPP example (may differ from daughter list).
    rows.append(("АО «НИКИМТ-Атомстрой» (EIS sample)", "7721632827"))
    seen = set()
    out = []
    for org, inn in rows:
        if inn not in seen:
            seen.add(inn)
            out.append((org, inn))
    return out
