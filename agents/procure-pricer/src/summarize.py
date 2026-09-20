# -*- coding: utf-8 -*-
"""
服务端聚合。

这是本项目相对原始 Skill 的核心改造点：原 Skill 硬性要求「模型心算」近千条数据
的均价与区间，误差不可控。这里改为由检索层直接返回聚合结果，模型只负责措辞，
不再承担算术。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Sequence


def _pct(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo, hi = int(pos), min(int(pos) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def aggregate(items: Sequence[Dict], price_field: str = "price_incl_tax") -> Dict:
    prices = [float(r[price_field]) for r in items]
    agg: Dict = {
        "count": len(items),
        "price_field": price_field,
        "min": round(min(prices), 2) if prices else 0.0,
        "max": round(max(prices), 2) if prices else 0.0,
        "avg": round(sum(prices) / len(prices), 2) if prices else 0.0,
        "median": round(_pct(prices, 0.5), 2) if prices else 0.0,
        "p25": round(_pct(prices, 0.25), 2) if prices else 0.0,
        "p75": round(_pct(prices, 0.75), 2) if prices else 0.0,
    }

    by_supplier: Dict[str, List[float]] = defaultdict(list)
    by_region: Dict[str, List[float]] = defaultdict(list)
    by_brand: Dict[str, List[float]] = defaultdict(list)
    by_month: Dict[str, List[float]] = defaultdict(list)

    for r, p in zip(items, prices):
        by_supplier[r["supplier_name"]].append(p)
        by_region[r["region"]].append(p)
        by_brand[r["brand"]].append(p)
        by_month[r["record_date"][:7]].append(p)

    def _top(d: Dict[str, List[float]], n: int):
        out = [{"name": k, "count": len(v), "avg": round(sum(v) / len(v), 2)}
               for k, v in d.items()]
        out.sort(key=lambda x: -x["count"])
        return out[:n]

    agg["top_suppliers"] = _top(by_supplier, 5)
    agg["top_regions"] = _top(by_region, 5)
    agg["top_brands"] = _top(by_brand, 5)
    agg["monthly"] = [
        {"month": m, "count": len(by_month[m]), "avg": round(sum(by_month[m]) / len(by_month[m]), 2)}
        for m in sorted(by_month)
    ]
    return agg


def sparkline(monthly: List[Dict], width: int = 40) -> str:
    """把月度均价压成一行文本迷你趋势图，便于在终端/聊天窗口直接看趋势。"""
    if len(monthly) < 2:
        return ""
    vals = [m["avg"] for m in monthly]
    lo, hi = min(vals), max(vals)
    blocks = "▁▂▃▄▅▆▇█"
    if hi - lo < 1e-9:
        return blocks[0] * len(vals)
    line = "".join(blocks[min(int((v - lo) / (hi - lo) * (len(blocks) - 1)), len(blocks) - 1)] for v in vals)
    return f"{monthly[0]['month']} {line} {monthly[-1]['month']}  (低 {lo:.2f} / 高 {hi:.2f})"


def to_markdown(agg: Dict, filters: Dict) -> str:
    """把聚合结果渲染成面向用户的中文总结（对应 Skill 要求的「文字总结」环节）。"""
    if agg["count"] == 0:
        return "未匹配到价格数据。"
    cond = "、".join(f"{k}={v}" for k, v in filters.items() if v) or "无附加条件"
    lines = [
        f"命中 **{agg['count']}** 条采购价格记录（筛选条件：{cond}），价格口径为含税单价。",
        f"- 价格区间：**{agg['min']} ~ {agg['max']}** 元，均价 **{agg['avg']}** 元，中位数 **{agg['median']}** 元（P25 {agg['p25']} / P75 {agg['p75']}）",
    ]
    if agg["top_suppliers"]:
        s = "、".join(f"{x['name']}（{x['count']} 条，均价 {x['avg']}）" for x in agg["top_suppliers"][:3])
        lines.append(f"- 主要供应商：{s}")
    if agg["top_regions"]:
        s = "、".join(f"{x['name']}（{x['count']} 条，均价 {x['avg']}）" for x in agg["top_regions"][:3])
        lines.append(f"- 主要地区：{s}")
    if agg["top_brands"]:
        s = "、".join(f"{x['name']}（{x['count']} 条，均价 {x['avg']}）" for x in agg["top_brands"][:3])
        lines.append(f"- 主要品牌：{s}")
    return "\n".join(lines)
