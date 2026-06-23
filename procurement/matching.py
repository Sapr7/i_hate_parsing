# -*- coding: utf-8 -*-
"""Flexible text matching for noisy EIS / ETP procurement titles."""
from __future__ import annotations

import re
from typing import Iterable, List, Sequence

# Extra AES / NPP objects not always present in reference Excel.
EXTRA_OBJECTS = [
    "Белорусская АЭС",
]

OBJECT_ALIASES = {
    "нововоронежская аэс-2": ["нваэс-2", "нововоронеж", "нваэс"],
    "ленинградская аэс-2": ["лаэс-2", "ленинградск", "сосновый бор"],
    "курская аэс-2": ["куаэс-2", "курск-2", "курской аэс-2"],
    "смоленская аэс-2": ["саэс-2", "десногорск"],
    "кольская аэс-2": ["каэс-2", "полярные зори"],
    "белоярская аэс-5": ["бн-1200", "заречный"],
    "якутская асмм": ["усть-куйга", "ритм-200"],
    "аэс «аккую»": ["аккую", "akkuyu"],
    "аэс «руппур»": ["руппур", "rooppur"],
    "аэс «эль-дабаа»": ["эль-дабаа", "el-dabaa", "dabaa"],
    "аэс «пакш-2»": ["пакш", "paks", "пакш-5", "пакш-6"],
    "аэс «куданкулам»": ["куданкулам", "kudankulam"],
    "белорусская аэс": ["белорус", "островец", "bn-1200", "белорусск"],
    "аэс «сюйдапу»": ["сюйдапу", "xudabao", "xudapu"],
    "приморская аэс": ["primorsk", "primorskaya"],
    "курская аэс": ["курская аэс", "курскую аэс"],
    "армянская аэс": ["армен", "мetsamor"],
    "тяньваньская аэс": ["tianwan", "тяньван"],
}

# Roots long enough to match after compact normalization.
ROOT_MIN_LEN = 5


def normalize_text(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[«»\"'`]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compact_text(text: str) -> str:
    return re.sub(r"\s+", "", normalize_text(text))


def object_tokens(name: str) -> List[str]:
    tokens = [normalize_text(name)]
    if "«" in name and "»" in name:
        quoted = name.split("«", 1)[1].split("»", 1)[0].strip()
        if quoted:
            tokens.extend([normalize_text(quoted), f"аэс {normalize_text(quoted)}"])
    low = normalize_text(name)
    for key, vals in OBJECT_ALIASES.items():
        if key in low:
            tokens.extend(vals)
    if "аэс" in low or "асмм" in low:
        tokens.append("аэс")
    uniq: List[str] = []
    seen = set()
    for tok in tokens:
        tok = tok.strip()
        if len(tok) < 3 or tok in seen:
            continue
        seen.add(tok)
        uniq.append(tok)
    return uniq


def _roots(tokens: Sequence[str]) -> List[str]:
    roots: List[str] = []
    for tok in tokens:
        tok = tok.strip()
        if len(tok) >= ROOT_MIN_LEN:
            roots.append(tok)
        elif tok in {"аэс", "асмм"}:
            roots.append(tok)
        else:
            # Short alias like "paks" -> keep as root if >=4
            if len(tok) >= 4:
                roots.append(tok)
    return list(dict.fromkeys(roots))


def loose_match(title: str, object_name: str) -> bool:
    """Broad capture: tolerate broken words and partial aliases."""
    if not title:
        return False
    t_norm = normalize_text(title)
    t_compact = compact_text(title)
    tokens = object_tokens(object_name)
    roots = _roots(tokens)

    # Full phrase in compact form (handles 'Белорусск ой' -> 'белорусской').
    for tok in tokens:
        if len(tok) >= 6 and compact_text(tok) in t_compact:
            return True

    # Object-specific roots: need at least one strong root hit.
    strong_hits = []
    for root in roots:
        if root in {"аэс", "асмм"}:
            continue
        if root in t_norm or compact_text(root) in t_compact:
            strong_hits.append(root)

    if not strong_hits:
        return False

    # For AES-named objects require AES marker somewhere unless root is very specific.
    low_obj = normalize_text(object_name)
    if "аэс" in low_obj or "асмм" in low_obj:
        if "аэс" not in t_compact and "асмм" not in t_compact and "аэс" not in t_norm:
            # Foreign projects sometimes omit 'АЭС' in title but use project name.
            quoted = ""
            if "«" in object_name and "»" in object_name:
                quoted = object_name.split("«", 1)[1].split("»", 1)[0].lower()
            if not quoted or quoted not in t_norm:
                return False
    return True


def strict_match(title: str, object_name: str) -> bool:
    """Legacy narrow filter kept for comparison."""
    if not title:
        return False
    t = normalize_text(title)
    tokens = object_tokens(object_name)
    return any(tok in t for tok in tokens if len(tok) > 5)


def match_any_object(title: str, objects: Iterable[str]) -> List[str]:
    return [name for name in objects if loose_match(title, name)]
