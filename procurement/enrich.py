# -*- coding: utf-8 -*-
from typing import Dict, List
from procurement.schema import TARGET_COLUMNS

def _blank():
    return {c: "" for c in TARGET_COLUMNS}

def eis_to_rows(eis_by_reg: Dict[str, dict]) -> List[dict]:
    rows = []
    for reg, item in eis_by_reg.items():
        objs = item.get("matched_objects") or []
        if isinstance(objs, set):
            objs = sorted(objs)
        obj = "; ".join(str(x) for x in objs[:2]) if objs else ""
        queries = item.get("queries") or []
        if isinstance(queries, set):
            queries = sorted(queries)
        row = _blank()
        row.update({
            "Object": obj,
            "Notice number": reg,
            "Description": item.get("title", ""),
            "Customer name": item.get("customer", ""),
            "EIS URL": item.get("url", ""),
            "Search query": "; ".join(str(q) for q in queries),
        })
        rows.append(row)
    return rows
