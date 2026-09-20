#!/usr/bin/env python3
"""日报生成：把通过质量红线的条目，组织成 11 个板块的科技情报日报。

两种模式：
  LLM 模式（设置 OPENAI_API_KEY）：调用兼容接口，prompt 见 templates/analysis_prompt.md
  模板模式（默认）：本地合成，字段靠品位，结构严格对齐 11 板块，保证零成本也能出完整日报

用法：
    python -m analysis.generate_report --date 2026-09-20
    OPENAI_API_KEY=sk-xxx python -m analysis.generate_report --date 2026-09-20 --llm
"""
import argparse
import json
import os
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.quality_gate import check_items, VIOLATION_TEXT

ROOT = Path(__file__).resolve().parents[1]
CN = timezone(timedelta(hours=8))

SECTIONS = ["核心动态", "今日速览", "今日金句", "信息分层", "YouTube 播客更新",
            "Twitter/X 精选", "趋势与关联", "行动建议", "待观察", "数据看板", "推荐阅读"]


def load_raw(date_str: str) -> dict:
    day = ROOT / "data" / "raw" / date_str
    def read(name):
        p = day / name
        return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else []
    return {"youtube": read("youtube.json"), "twitter": read("twitter.json")}


def yesterday_counts(date_str: str):
    """读取昨日数据用于「数据看板」板块的环比。没有昨日数据就返回 None，不编造。"""
    d = datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)
    p = ROOT / "data" / "raw" / d.strftime("%Y-%m-%d") / "summary.json"
    if not p.exists():
        return None
    try:
        s = json.loads(p.read_text(encoding="utf-8-sig"))
        return {"date": d.strftime("%Y-%m-%d"), "total": s.get("total_items", 0),
                "youtube": s.get("youtube_count", 0), "twitter": s.get("twitter_count", 0)}
    except json.JSONDecodeError:
        return None


def heat_of(item) -> str:
    """热度：用可观测信号算，不靠主观判断。

    信号：aged freshness（越新鲜越热）+ 是否含关键行动信号（发布/漏洞/定价/开源/限制）。
    """
    score = 0
    age = item.get("age_hours")
    if isinstance(age, (int, float)):
        score += 2 if age <= 6 else (1 if age <= 12 else 0)
    blob = f"{item.get('title','')}{item.get('summary','')}"
    hot = ["发布", "开源", "漏洞", "定价", "上线", "限制", "封禁", "下线", "降价", "收购"]
    score += min(2, sum(1 for k in hot if k in blob))
    return "🔥" * max(1, min(3, score))


def tier_of(item, rank: int) -> str:
    if rank < 3:
        return "⚡ 必看"
    if rank < 10:
        return "📖 速读"
    return "🔬 深读"


def compose_markdown(date_str: str, yt: list, tw: list, failed: list, prev: dict) -> str:
    L = []
    total = len(yt) + len(tw)

    L.append(f"# 科技情报日报 · {date_str}")
    L.append("")

    # 0 核心动态
    L.append("## 0. 核心动态")
    L.append("")
    if total == 0:
        L.append("今日无通过质量红线的新内容。")
    else:
        for it in (yt + tw)[:5]:
            who = it.get("channel") or it.get("author")
            L.append(f"- {who}：{it.get('title','')}（{(it.get('summary') or '').strip()[:60]}）")
    L.append("")

    # 1 今日速览
    L.append("## 1. 今日速览")
    L.append("")
    for it in sorted(yt + tw, key=lambda x: (x.get("age_hours") or 99))[:5]:
        L.append(f"- {heat_of(it)} {it.get('title','')} — {it.get('channel') or it.get('author')}")
    L.append("")

    # 2 今日金句
    L.append("## 2. 今日金句")
    L.append("")
    quote_src = max(tw, key=lambda t: len((t.get("summary") or ""))) if tw else None
    if quote_src:
        L.append(f"> {(quote_src.get('summary') or '').strip()}")
        L.append(f">")
        L.append(f"> —— {quote_src.get('author')}（{quote_src.get('handle','')}）[原文]({quote_src.get('link','#')})")
    else:
        L.append("今日无符合标准的金句条目。")
    L.append("")

    # 3 信息分层
    L.append("## 3. 信息分层")
    L.append("")
    ranked = sorted(yt + tw, key=lambda x: (x.get("age_hours") or 99))
    buckets = {"⚡ 必看": [], "📖 速读": [], "🔬 深读": []}
    for i, it in enumerate(ranked):
        buckets[tier_of(it, i)].append(it)
    for tier, items in buckets.items():
        L.append(f"### {tier}（{len(items)} 条）")
        L.append("")
        if not items:
            L.append("本档无内容。")
            L.append("")
            continue
        for it in items:
            src = it.get("channel") or it.get("author")
            L.append(f"- **{(it.get('title') or '').strip()}**")
            L.append(f"  - 来源：{src} ｜ 热度：{heat_of(it)} ｜ [链接]({it.get('link','#')})")
            L.append(f"  - 摘要：{(it.get('summary') or '').strip()}")
        L.append("")

    # 4 YouTube 播客更新
    L.append("## 4. YouTube 播客更新")
    L.append("")
    if yt:
        L.append("| 频道 | 主题 | 嘉宾/讲者 | 核心内容 | 时长 | 链接 |")
        L.append("|---|---|---|---|---|---|")
        for it in yt:
            L.append(f"| {it.get('channel','')} | {(it.get('title') or '').replace('|','/')} | "
                     f"{it.get('author','')} | {(it.get('summary') or '').replace('|','/')[:70]} | "
                     f"{it.get('duration','-')} | [观看]({it.get('link','#')}) |")
    else:
        L.append("今日无播客更新。")
    L.append("")

    # 5 Twitter/X 精选（按主题分组）
    L.append("## 5. Twitter/X 精选")
    L.append("")
    if tw:
        groups = {}
        for it in tw:
            groups.setdefault(it.get("domain") or "其他", []).append(it)
        for topic, items in groups.items():
            L.append(f"**{topic}**")
            L.append("")
            for it in items:
                L.append(f"- {it.get('author')}（{it.get('handle','')}）：{(it.get('summary') or '').strip()} [链接]({it.get('link','#')})")
            L.append("")
    else:
        L.append("今日无推文入选。")
        L.append("")

    # 6 趋势与关联
    L.append("## 6. 趋势与关联")
    L.append("")
    topics = Counter()
    for it in yt + tw:
        for kw in ["评测", "Agent", "沙箱", "冷启动", "上下文", "开源", "定价", "安全", "数据集"]:
            if kw in f"{it.get('title','')}{it.get('summary','')}":
                topics[kw] += 1
    cross = [(k, v) for k, v in topics.items() if v >= 2]
    if cross:
        L.append("跨来源共同话题（出现 ≥2 次）：")
        L.append("")
        for k, v in sorted(cross, key=lambda x: -x[1]):
            L.append(f"- **{k}**：{v} 个来源提及")
    else:
        L.append("今日无明显跨来源共同话题。")
    L.append("")

    # 7 行动建议
    L.append("## 7. 行动建议")
    L.append("")
    actions = [it for it in yt + tw if any(k in f"{it.get('title','')}{it.get('summary','')}"
                                           for k in ["发布", "漏洞", "定价", "上线", "开源", "限制"])]
    if actions:
        for it in actions[:3]:
            L.append(f"- 评估 **{(it.get('title') or '').strip()[:24]}** 对现有方案的影响，[来源]({it.get('link','#')})")
    else:
        L.append("今日无需立即执行的动作。")
    L.append("")

    # 8 待观察
    L.append("## 8. 待观察（未来 1-3 天）")
    L.append("")
    watch = [k for k, v in topics.items() if v == 1][:3]
    L.extend([f"- {w}：今日仅单一来源提及，待更多来源交叉验证" for w in watch] or ["- 暂无"])
    L.append("")

    # 9 数据看板
    L.append("## 9. 数据看板")
    L.append("")
    L.append("| 指标 | 今日 | 昨日 | 变化 |")
    L.append("|---|---:|---:|---|")
    if prev:
        rows = [("总条目数", total, prev["total"]),
                ("YouTube", len(yt), prev["youtube"]),
                ("Twitter/X", len(tw), prev["twitter"])]
        for name, today, yday in rows:
            if yday:
                pct = (today - yday) / yday * 100
                delta = f"{pct:+.0f}%"
            else:
                delta = "—"
            L.append(f"| {name} | {today} | {yday} | {delta} |")
    else:
        L.append(f"| 总条目数 | {total} | — | 无昨日数据 |")
        L.append(f"| YouTube | {len(yt)} | — | 无昨日数据 |")
        L.append(f"| Twitter/X | {len(tw)} | — | 无昨日数据 |")
    L.append("")

    # 10 推荐阅读
    L.append("## 10. 推荐阅读")
    L.append("")
    for it in (buckets["🔬 深读"] or buckets["📖 速读"])[:3]:
        title = (it.get("title") or "").strip()
        L.append(f"- [{title}]({it.get('link', '#')}) — {it.get('channel') or it.get('author')}")
    L.append("")

    # 附录：质量红线拦截情况（对外透明）
    L.append("---")
    L.append("")
    L.append(f"## 附录 · 质量红线拦截（{len(failed)} 条）")
    L.append("")
    if failed:
        for f in failed:
            codes = "、".join(f"{c} {VIOLATION_TEXT.get(c,'')}" for c in f["violations"])
            L.append(f"- {(f['item'].get('title') or '')[:30]} → {codes}")
    else:
        L.append("今日全部条目通过五条质量红线。")
    L.append("")

    return "\n".join(L)


def call_llm(prompt: str, payload: dict, model: str, base_url: str, key: str):
    system = (ROOT / "templates" / "analysis_prompt.md").read_text(encoding="utf-8") or prompt
    body = json.dumps({"model": model, "temperature": 0.3,
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]}).encode()
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())["choices"][0]["message"]["content"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    ap.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    args = ap.parse_args()

    raw = load_raw(args.date)
    all_items = raw["youtube"] + raw["twitter"]
    passed, failed = check_items(all_items)
    yt = [i for i in passed if i.get("platform") == "youtube"]
    tw = [i for i in passed if i.get("platform") == "twitter"]
    print(f"[ok] 质量红线：通过 {len(passed)} / 拦截 {len(failed)}")

    prev = yesterday_counts(args.date)
    if args.llm and os.getenv("OPENAI_API_KEY"):
        try:
            md = call_llm("", {"youtube": yt, "twitter": tw}, args.model, args.base_url, os.environ["OPENAI_API_KEY"])
            print("[ok] LLM 模式生成")
        except Exception as exc:
            print(f"[warn] LLM 调用失败，降级模板模式：{exc}", file=sys.stderr)
            md = compose_markdown(args.date, yt, tw, failed, prev)
    else:
        md = compose_markdown(args.date, yt, tw, failed, prev)
        print("[ok] 模板模式生成")

    out_dir = ROOT / "data" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{args.date}.md"
    out.write_text(md, encoding="utf-8")
    print(f"[done] 日报 -> {out.relative_to(ROOT)}（{len(md)} 字符）")
    missing = [s for s in SECTIONS if s not in md]
    print(f"[check] 板块完整性：{11 - len(missing)}/11" + (f" 缺失：{missing}" if missing else ""))


if __name__ == "__main__":
    main()
