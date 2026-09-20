# -*- coding: utf-8 -*-
"""
模拟价格库查询接口（price.query）：唯一查价入口。

行为对齐真实检索接口：
  - 各维度以包含匹配（contains）语义做模糊过滤
  - 服务端先 count 再分支：EMPTY / TOO_MANY(>=1000) / LIST
  - LIST 时返回 items、服务端聚合结果（aggregate）、明细文件下载路径（download_path）
"""
from __future__ import annotations

import csv
import os
import uuid
from typing import Dict, List, Optional, Sequence

from summarize import aggregate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "out")

TOO_MANY_THRESHOLD = 1000


def _contains(field_value: str, needle: str) -> bool:
    """包含匹配语义：字段值包含过滤值即命中（大小写不敏感）。"""
    if not needle:
        return True
    return needle.lower() in (field_value or "").lower()


def query_material_prices(
    rows: Sequence[Dict],
    category: Optional[str] = None,
    material_desc: Optional[str] = None,
    supplier_name: Optional[str] = None,
    brand: Optional[str] = None,
    spec: Optional[str] = None,
    region: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    export: bool = True,
) -> Dict:
    hits: List[Dict] = []
    for r in rows:
        if not _contains(r["category"], category):
            continue
        if not _contains(r["material_desc"], material_desc):
            continue
        if not _contains(r["supplier_name"], supplier_name):
            continue
        if not _contains(r["brand"], brand):
            continue
        if not _contains(r["spec"], spec):
            continue
        if not _contains(r["region"], region):
            continue
        if date_start and r["record_date"] < date_start:
            continue
        if date_end and r["record_date"] > date_end:
            continue
        hits.append(r)

    total = len(hits)
    filters = {
        "category": category, "material_desc": material_desc, "supplier_name": supplier_name,
        "brand": brand, "spec": spec, "region": region,
        "date_range": f"{date_start or ''}~{date_end or ''}" if (date_start or date_end) else None,
    }

    if total == 0:
        return {"action": "EMPTY", "total": 0, "items": [], "filters": filters, "aggregate": None}

    if total >= TOO_MANY_THRESHOLD:
        return {
            "action": "TOO_MANY", "total": total, "items": [], "filters": filters,
            "aggregate": None,
            "hint": "结果过多，请补充品类/物料/供应商/地区/时间条件后重试",
        }

    download_path = None
    if export:
        os.makedirs(OUT_DIR, exist_ok=True)
        fname = f"detail_{uuid.uuid4().hex[:8]}.csv"
        download_path = os.path.join(OUT_DIR, fname)
        with open(download_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(hits[0].keys()))
            w.writeheader()
            w.writerows(hits)

    return {
        "action": "LIST",
        "total": total,
        "items": hits,
        "filters": {k: v for k, v in filters.items()},
        "aggregate": aggregate(hits),
        "download_path": download_path,
    }
