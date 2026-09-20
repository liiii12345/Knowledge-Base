# -*- coding: utf-8 -*-
"""由评测结果生成可视化报告：python eval/build_report.py -> eval/report.html"""
import json
import os
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUR = json.load(open(os.path.join(ROOT, "eval", "results.json"), encoding="utf-8"))
try:
    V1 = json.load(open(os.path.join(ROOT, "eval", "results_v1.json"), encoding="utf-8"))
except FileNotFoundError:
    V1 = None


def pct(x):
    return f"{x * 100:.1f}%"


ACTION_LABEL = {"LIST": "返回结果", "TOO_MANY": "结果过多", "EMPTY": "无匹配", "ASK": "追问条件"}

rows_html = []
for r in CUR["records"]:
    g = r["gated"]
    ok = g["action"] == r["oracle_action"]
    badge = "pass" if ok else "fail"
    diff = "、".join(f"{k}: 期望 {v['want']} / 实得 {v['got']}"
                    for k, v in g["filter_detail"].items() if v["want"] != v["got"]) or "—"
    rows_html.append(f"""      <tr>
        <td class="id">{r['id']}</td>
        <td class="q">{r['query']}</td>
        <td>{ACTION_LABEL.get(r['oracle_action'], r['oracle_action'])}</td>
        <td><span class="tag {badge}">{ACTION_LABEL.get(g['action'], g['action'])}</span></td>
        <td><span class="tag fail">{ACTION_LABEL.get(r['naive']['action'], r['naive']['action'])}</span></td>
        <td class="num">{g['calls']}</td>
        <td class="diff">{diff}</td>
      </tr>""")

v1_block = ""
if V1:
    v1_block = f"""
    <section>
      <h2>迭代收益</h2>
      <p class="lead">第一轮评测暴露三个失效模式，其中两个属于解析层缺陷，修复后重测。</p>
      <table class="cmp">
        <thead><tr><th>轮次</th><th>action 一致率</th><th>过滤条件准确率</th><th>门控合规率</th><th>本轮修复</th></tr></thead>
        <tbody>
          <tr><td>v1</td><td class="num">{pct(V1['gated']['action_accuracy'])}</td>
              <td class="num">{pct(V1['gated']['filter_accuracy'])}</td>
              <td class="num">{pct(V1['gated']['gate_compliance'])}</td><td>—</td></tr>
          <tr class="hi"><td>v2（当前）</td><td class="num">{pct(CUR['gated']['action_accuracy'])}</td>
              <td class="num">{pct(CUR['gated']['filter_accuracy'])}</td>
              <td class="num">{pct(CUR['gated']['gate_compliance'])}</td>
              <td>地区简称（沪/粤/鲁…）、<code>上个月</code> 时间解析</td></tr>
        </tbody>
      </table>
    </section>"""

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>采购询价 Agent · 评测报告</title>
<style>
  :root {{
    --blue: #1a56db; --blue-d: #1e3a8a; --blue-l: #eff6ff; --blue-b: #dbeafe;
    --ink: #111827; --sub: #4b5563; --line: #e5e7eb; --bg: #f8fafc;
    --ok: #047857; --ok-bg: #ecfdf5; --bad: #b91c1c; --bad-bg: #fef2f2;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
    line-height:1.65; }}
  .wrap {{ max-width:1120px; margin:0 auto; padding:48px 28px 72px; }}
  header {{ border-left:5px solid var(--blue); padding-left:20px; margin-bottom:36px; }}
  h1 {{ font-size:27px; margin:0 0 8px; letter-spacing:-.3px; }}
  .meta {{ color:var(--sub); font-size:13px; }}
  h2 {{ font-size:18px; margin:38px 0 14px; padding-bottom:9px; border-bottom:2px solid var(--blue-b); }}
  .lead {{ color:var(--sub); margin:0 0 16px; font-size:14px; }}
  .cards {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin:20px 0 6px; }}
  .card {{ background:#fff; border:1px solid var(--line); border-radius:10px; padding:18px 16px; }}
  .card .k {{ font-size:12px; color:var(--sub); margin-bottom:6px; }}
  .card .v {{ font-size:29px; font-weight:650; color:var(--blue-d); letter-spacing:-.5px; }}
  .card .d {{ font-size:12px; color:var(--sub); margin-top:5px; }}
  table {{ width:100%; border-collapse:collapse; background:#fff; font-size:13.5px;
    border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
  th {{ background:var(--blue-l); color:var(--blue-d); text-align:left; padding:11px 13px;
    font-weight:600; font-size:12.5px; border-bottom:1px solid var(--blue-b); }}
  td {{ padding:10px 13px; border-bottom:1px solid var(--line); vertical-align:top; }}
  tr:last-child td {{ border-bottom:none; }}
  tbody tr:hover {{ background:#f9fafb; }}
  .cmp td, .cmp th {{ text-align:center; }}
  .cmp td:first-child, .cmp th:first-child {{ text-align:left; }}
  .cmp tr.hi {{ background:var(--blue-l); }}
  .num {{ text-align:center; font-variant-numeric:tabular-nums; font-weight:600; }}
  .id {{ color:var(--sub); font-variant-numeric:tabular-nums; width:38px; }}
  .q {{ max-width:280px; }}
  .diff {{ color:var(--sub); font-size:12.5px; max-width:250px; }}
  .tag {{ display:inline-block; padding:2px 9px; border-radius:20px; font-size:12px; font-weight:600;
    white-space:nowrap; }}
  .tag.pass {{ background:var(--ok-bg); color:var(--ok); }}
  .tag.fail {{ background:var(--bad-bg); color:var(--bad); }}
  code {{ background:#f1f5f9; padding:1px 6px; border-radius:4px; font-size:12.5px; }}
  .note {{ background:#fff; border:1px solid var(--line); border-left:4px solid var(--blue);
    border-radius:8px; padding:14px 18px; font-size:13.5px; color:var(--sub); }}
  .note b {{ color:var(--ink); }}
  footer {{ margin-top:44px; padding-top:18px; border-top:1px solid var(--line);
    font-size:12.5px; color:var(--sub); }}
  @media(max-width:820px){{ .cards{{grid-template-columns:repeat(2,1fr);}} }}
</style>
</head>
<body><div class="wrap">
<header>
  <h1>采购询价 Agent · 评测报告</h1>
  <div class="meta">{CUR['cases']} 条用例 · 生成于 {date.today().isoformat()} · 数据源：脚本生成的脱敏样本库 25,920 条</div>
</header>

<section>
  <h2>结论</h2>
  <div class="cards">
    <div class="card"><div class="k">action 一致率</div><div class="v">{pct(CUR['gated']['action_accuracy'])}</div>
      <div class="d">基线 {pct(CUR['naive']['action_accuracy'])}</div></div>
    <div class="card"><div class="k">空结果率</div><div class="v">{pct(CUR['gated']['empty_rate'])}</div>
      <div class="d">基线 {pct(CUR['naive']['empty_rate'])}</div></div>
    <div class="card"><div class="k">平均检索调用</div><div class="v">{CUR['gated']['avg_calls']:.2f}</div>
      <div class="d">上限 5 次，实测峰值 {CUR['gated']['max_calls']} 次</div></div>
    <div class="card"><div class="k">门控合规率</div><div class="v">{pct(CUR['gated']['gate_compliance'])}</div>
      <div class="d">逐维比对「该查 / 不该查」</div></div>
  </div>
  <div class="note" style="margin-top:16px">
    <b>基线为什么崩：</b>无门控方案对每个维度都发起召回，并用用户原话直接当过滤值。用户说「纸巾盒」，
    库里是「纸巾盒子」，原话直传的结果就是零命中——{pct(CUR['naive']['empty_rate'])} 的查询查了个寂寞，
    且这些失败全部静默发生，用户只会以为「库里没数据」。
  </div>
</section>

{v1_block}

<section>
  <h2>逐用例明细</h2>
  <p class="lead">oracle = 用人工标注的过滤条件直接查库得到的标准答案；gated = 本方案；naive = 无门控基线。</p>
  <table>
    <thead><tr><th>#</th><th>问句</th><th>oracle</th><th>gated</th><th>naive</th><th>调用</th><th>偏差</th></tr></thead>
    <tbody>
{chr(10).join(rows_html)}
    </tbody>
  </table>
</section>

<section>
  <h2>残留缺口</h2>
  <div class="note">
    <b>错别字导致召回失败</b>（用例 37：<code>抛柚砖</code>）：分类召回为 0，Agent 退化为追问。
    这不属于解析层缺陷——「抛柚砖→抛釉砖」需要知识库维护别名表，靠改提示词或调阈值都解决不了。
    区分「模型问题 / 解析问题 / 数据问题」是本项目的一条方法论：三层问题的处置方式完全不同，
    混在一起处理的结局就是不停堆提示词。
  </div>
</section>

<footer>
  报告由 <code>eval/build_report.py</code> 从 <code>eval/results.json</code> 生成，
  重跑 <code>python eval/run_eval.py && python eval/build_report.py</code> 即可复现。
  数据全部为脚本生成的虚构样本，不含任何真实企业数据。
</footer>
</div></body></html>
"""

out = os.path.join(ROOT, "eval", "report.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print(f"报告已生成 -> {out}")
