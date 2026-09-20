# -*- coding: utf-8 -*-
"""
端到端入口：中文问句 -> 规范值 -> 查价 -> 文字总结 + 明细下载。

用法：
    python src/cli.py "山东省惠达抛釉砖近半年的采购价"
    python src/cli.py "查一下价格"
    python src/cli.py --debug "章丘市明水义和印纸巾盒价格变化"
"""
from __future__ import annotations

import csv
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from matcher import build_matchers          # noqa: E402
from intent_parser import parse_query       # noqa: E402
from query_engine import query_material_prices  # noqa: E402
from summarize import to_markdown, sparkline    # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "price_library.csv")


def load_rows():
    with open(DATA, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def run(query_text: str, today: date = None, debug: bool = False) -> str:
    rows = load_rows()
    matchers = build_matchers(rows)
    brands = sorted({r["brand"] for r in rows})
    suppliers = sorted({r["supplier_name"] for r in rows})
    today = today or date(2026, 8, 31)

    parsed = parse_query(query_text, matchers, brands, suppliers, today)

    if debug:
        print("--- 意图门控决策 ---")
        for d in parsed.decisions:
            print(f"  [{d['gate']}] {d['dim']:<14} {d['value'] or '-':<28} {d['reason']}")
        print(f"  MCP 调用次数（估算）：{parsed.calls}")
        print()

    if not any(v for k, v in parsed.filters.items() if k not in ("date_start", "date_end")):
        return ("未能从话术中解析出任何查询条件，请补充物料/品类/供应商/品牌/规格/地区/时间中的至少一项。\n"
                "示例：「山东省惠达抛釉砖近半年的采购价」")

    f = parsed.filters
    result = query_material_prices(
        rows,
        category=f["category"], material_desc=f["material_desc"],
        supplier_name=f["supplier_name"], brand=f["brand"], spec=f["spec"],
        region=f["region"], date_start=f["date_start"], date_end=f["date_end"],
    )

    if result["action"] == "EMPTY":
        cond = "、".join(f"{k}={v}" for k, v in result["filters"].items() if v) or "无条件"
        return f"未匹配到价格数据（{cond}）。建议放宽条件后重试。"
    if result["action"] == "TOO_MANY":
        return f"命中 {result['total']} 条，超过单次返回上限，请补充品类/物料/供应商/地区/时间条件后重试。"

    agg = result["aggregate"]
    out = [to_markdown(agg, result["filters"])]
    if len(agg["monthly"]) >= 2:
        out.append("")
        out.append("月度均价趋势：" + sparkline(agg["monthly"]))
    if result.get("download_path"):
        rel = os.path.relpath(result["download_path"], ROOT).replace("\\", "/")
        out.append("")
        out.append(f"源数据明细：[点击下载]({rel})")
    return "\n".join(out)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    debug = "--debug" in args
    args = [a for a in args if a != "--debug"]
    if not args:
        print(__doc__)
        sys.exit(1)
    print(run(args[0], debug=debug))
