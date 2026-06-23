# -*- coding: utf-8 -*-
"""
Heuristic quality filter (placeholder for future Bothub API).
Returns: keep | review | reject with short reason.
"""
from __future__ import annotations

import re
from typing import Dict, Tuple

from procurement.matching import normalize_text

# Obvious noise even in loose capture mode.
HARD_REJECT = re.compile(
    r"услуг(?:и|а)\s+(?:по\s+)?(?:страхован|консульт|обучен|охран|"
    r"техническ(?:ой|ая)\s+поддерж|сопровожд)|"
    r"страхован(?:ие|ия)|"
    r"доступ\s+к\s+баз(?:е|ам)\s+данн|"
    r"мониторинг\s+цен|"
    r"запрос\s+коммерческ(?:их|ого)\s+предлож|"
    r"аренд(?:а|ы)\s+(?:помещ|офис|склад)|"
    r"канцеляр|"
    r"полиграф",
    re.I,
)

SOFT_REJECT = re.compile(
    r"проектир(?:ование|овоч)|"
    r"изыск(?:ан|атель)|"
    r"экспертиз(?:а|ы)|"
    r"\bпир\b|"
    r"разработк(?:а|и)\s+(?:рабоч|проект)|"
    r"научно-исследов",
    re.I,
)

NPP_SUPPLY = re.compile(
    r"поставк|изготовлен|монтаж|оборудован|материал|комплект|"
    r"трубопровод|арматур|кабель|насос|клапан|задвижк|"
    r"сантех|санфаянс|металл|конструкц|блок\s*№|энергоблок|"
    r"реактор|турбин|генератор|теплообмен|здани|сооружен",
    re.I,
)

NPP_CODES = re.compile(r"\b\d{2}[A-Z]{2,4}\b|\b\d{1,2}[Uu][A-Za-z]{2,4}\b|энергоблок", re.I)


def classify(title: str, matched_objects: list, customer: str = "") -> Tuple[str, str]:
    """
    keep   — likely relevant procurement for AES construction/supply
    review — ambiguous, keep in dataset for later AI pass
    reject — likely noise
    """
    if not title:
        return "reject", "empty title"

    t = normalize_text(title)
    cust = normalize_text(customer)

    if HARD_REJECT.search(t):
        return "reject", "hard noise pattern"

    if not matched_objects and not any(
        x in t for x in ("аэс", "асмм", "энергоблок", "реактор", "атомн")
    ):
        return "reject", "no object link"

    if SOFT_REJECT.search(t) and not NPP_SUPPLY.search(t):
        return "review", "engineering/services wording"

    if matched_objects:
        if NPP_SUPPLY.search(t) or NPP_CODES.search(t):
            return "keep", "object + supply markers"
        if any(x in t for x in ("аэс", "асмм", "энергоблок")):
            return "keep", "object + npp marker"
        return "review", "object matched, weak supply signal"

    if any(x in cust for x in ("атом", "росатом", "аэс", "никимт", "атомстрой")):
        if NPP_SUPPLY.search(t):
            return "review", "atom customer + supply"
        return "review", "atom customer only"

    return "reject", "no match"


def apply_filter(record: Dict) -> Dict:
    verdict, reason = classify(
        record.get("title", ""),
        record.get("matched_objects", []),
        record.get("customer", ""),
    )
    record["ai_verdict"] = verdict
    record["ai_reason"] = reason
    return record
