# -*- coding: utf-8 -*-
"""
评测：意图门控方案 vs 无门控基线。

评测方法论：
  1. 每条用例人工标注「正确的过滤条件」（expect）
  2. 由 expect 直接查库得到 oracle action（人工标注条件下的真实结果）
  3. 分别跑 gated（本方案）与 naive（无门控 + 用户原话直传 filter）两条管线
  4. 对比指标：门控合规率、过滤条件准确率、action 一致率、调用次数、空结果率

运行：python eval/run_eval.py
输出：eval/results.json
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from matcher import build_matchers                    # noqa: E402
from intent_parser import parse_query, STOPWORDS      # noqa: E402
from query_engine import query_material_prices        # noqa: E402

CASES = os.path.join(ROOT, "eval", "cases.jsonl")
RESULT = os.path.join(ROOT, "eval", "results.json")
TODAY = date(2026, 8, 31)


def load_rows():
    with open(os.path.join(ROOT, "data", "price_library.csv"), encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _raw_fragment(text: str) -> str:
    """naive 基线：整句去停用词后直接当过滤值（不做规范化、不做维度拆分）。"""
    s = text
    for w in STOPWORDS:
        s = s.replace(w, "")
    return re.sub(r"[，。、？?！!；;：:\s]+", "", s)


def naive_pipeline(query_text: str, rows, matchers):
    """无门控基线：两个维度一律 match，且用用户原话直传 filter。"""
    frag = _raw_fragment(query_text)
    matchers["category"].match(frag, top_k=1)     # 调了但不用返回值
    matchers["supplier"].match(frag, top_k=1)
    return {
        "filters": {"category": frag or None, "supplier_name": frag or None},
        "calls": 2,
        "gate_violations": 1 if frag else 0,   # 至少有一个维度是伪造的
    }


def gated_pipeline(query_text: str, rows, matchers, brands, suppliers):
    p = parse_query(query_text, matchers, brands, suppliers, TODAY)
    return {"filters": p.filters, "calls": p.calls, "decisions": p.decisions,
            "parsed": p}


def run(rows, matchers, brands, suppliers, filters: dict):
    return query_material_prices(rows, export=False, **filters)


def main():
    rows = load_rows()
    matchers = build_matchers(rows)
    brands = sorted({r["brand"] for r in rows})
    suppliers = sorted({r["supplier_name"] for r in rows})

    cases = [json.loads(l) for l in open(CASES, encoding="utf-8") if l.strip()]
    records = []

    for c in cases:
        q, expect = c["query"], c.get("expect", {})
        expect_gate = c.get("expect_gate", {})

        # --- oracle：人工标注条件下的真实结果 ---
        if expect:
            oracle_filters = {k: v for k, v in expect.items() if v is not None}
            oracle = run(rows, matchers, brands, suppliers, oracle_filters)
            oracle_action = oracle["action"]
        else:
            oracle_action = "ASK"

        # --- gated ---
        g = gated_pipeline(q, rows, matchers, brands, suppliers)
        gf = g["filters"]
        if not any(v for k, v in gf.items() if k != "date_start" and k != "date_end"):
            g_action = "ASK"
        else:
            g_action = run(rows, matchers, brands, suppliers,
                           {k: v for k, v in gf.items() if v})["action"]

        # 门控合规：expect_gate 中标注的每个维度，实际 gate 是否一致
        gate_map = {}
        for d in g["decisions"]:
            gate_map.setdefault(d["dim"], []).append(d["gate"])
        gate_ok = True
        gate_detail = {}
        for dim, want in expect_gate.items():
            got = gate_map.get(dim, ["-"])[-1]
            gate_detail[dim] = {"want": want, "got": got}
            if got != want:
                gate_ok = False

        # 过滤条件准确：expect 中每个键的值是否与解析结果一致
        filter_ok = True
        filter_detail = {}
        for k, want in expect.items():
            got = gf.get(k)
            filter_detail[k] = {"want": want, "got": got}
            if want != got:
                filter_ok = False

        # --- naive ---
        n = naive_pipeline(q, rows, matchers)
        n_action = run(rows, matchers, brands, suppliers,
                       {k: v for k, v in n["filters"].items() if v})["action"]

        records.append({
            "id": c["id"], "query": q,
            "oracle_action": oracle_action,
            "gated": {"action": g_action, "calls": g["calls"], "filters": {k: v for k, v in gf.items() if v},
                      "gate_ok": gate_ok, "gate_detail": gate_detail,
                      "filter_ok": filter_ok, "filter_detail": filter_detail},
            "naive": {"action": n_action, "calls": n["calls"], "filters": n["filters"]},
        })

    n_total = len(records)
    gated = {
        "gate_compliance": sum(r["gated"]["gate_ok"] for r in records) / n_total,
        "filter_accuracy": sum(r["gated"]["filter_ok"] for r in records) / n_total,
        "action_accuracy": sum(r["gated"]["action"] == r["oracle_action"] for r in records) / n_total,
        "empty_rate": sum(r["gated"]["action"] == "EMPTY" for r in records) / n_total,
        "avg_calls": sum(r["gated"]["calls"] for r in records) / n_total,
        "max_calls": max(r["gated"]["calls"] for r in records),
    }
    naive = {
        "action_accuracy": sum(r["naive"]["action"] == r["oracle_action"] for r in records) / n_total,
        "empty_rate": sum(r["naive"]["action"] == "EMPTY" for r in records) / n_total,
        "avg_calls": sum(r["naive"]["calls"] for r in records) / n_total,
    }

    summary = {
        "cases": n_total,
        "gated": {k: round(v, 4) if isinstance(v, float) else v for k, v in gated.items()},
        "naive": {k: round(v, 4) if isinstance(v, float) else v for k, v in naive.items()},
        "records": records,
    }
    with open(RESULT, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # --- 控制台输出 ---
    print(f"{'ID':<3} {'问句':<34} {'oracle':<9} {'gated':<9} {'naive':<9} {'调用':<4} {'门控':<4} {'条件':<4}")
    print("-" * 96)
    for r in records:
        flags = f"{'OK' if r['gated']['gate_ok'] else 'X':<4}{'OK' if r['gated']['filter_ok'] else 'X':<4}"
        print(f"{r['id']:<3} {r['query'][:32]:<34} {r['oracle_action']:<9} "
              f"{r['gated']['action']:<9} {r['naive']['action']:<9} {r['gated']['calls']:<4} {flags}")
    print()
    print("指标                 gated（本方案）      naive（无门控基线）")
    print(f"action 一致率         {gated['action_accuracy']:>10.1%}          {naive['action_accuracy']:>10.1%}")
    print(f"空结果率             {gated['empty_rate']:>10.1%}          {naive['empty_rate']:>10.1%}")
    print(f"平均 MCP 调用次数     {gated['avg_calls']:>10.2f}          {naive['avg_calls']:>10.2f}")
    print(f"门控合规率           {gated['gate_compliance']:>10.1%}          {'—':>10}")
    print(f"过滤条件准确率       {gated['filter_accuracy']:>10.1%}          {'—':>10}")
    print(f"\n明细已写入 {RESULT}")


if __name__ == "__main__":
    main()
