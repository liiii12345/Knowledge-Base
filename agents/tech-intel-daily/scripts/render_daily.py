#!/usr/bin/env python3
"""渲染：把结构化条目渲染成可转发的 Markdown 日报。

用法：
    python scripts/render_daily.py --date 2026-09-03
    python scripts/render_daily.py --date 2026-09-03 --out output/my-daily.md
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def render(items: dict) -> str:
    date_str = items.get("date", "")
    kept = items.get("kept", [])
    dropped = items.get("dropped", [])
    mode = items.get("mode", "rule")

    p0 = [i for i in kept if i.get("priority") == "P0"]
    p1 = [i for i in kept if i.get("priority") == "P1"]
    p2 = [i for i in kept if i.get("priority") == "P2"]
    for group in (p0, p1, p2):
        group.sort(key=lambda x: -(x.get("confidence") or 0))

    lines = []
    lines.append(f"# 科技情报日报 · {date_str}")
    lines.append("")

    if p0:
        top = p0[0]
        lines.append(f"> 今日最值得关注：{top.get('headline', '')}｜{top.get('one_liner', '')}")
    elif p1:
        lines.append(f"> 今日无 P0 事项，最值得看的是：{p1[0].get('headline', '')}")
    else:
        lines.append("> 今日无 P0 / P1 事项，只有背景信息。")
    lines.append("")
    lines.append(f"<!-- 生成模式：{mode} ｜ 保留 {len(kept)} 条 ｜ 丢弃 {len(dropped)} 条 -->")
    lines.append("")

    def render_item(it):
        conf = it.get("confidence") or 0
        flag = "　⚠️ 待核实" if conf < 0.6 else ""
        out = [f"### {it.get('headline','无标题')}{flag}", ""]
        out.append(f"- **事实**：{it.get('one_liner','')}")
        out.append(f"- **影响**：{it.get('why_it_matters','')}")
        if it.get("action"):
            out.append(f"- **建议**：{it.get('action')}")
        out.append(f"- 来源：[{it.get('source','未知')}]({it.get('source_link','#')}) ｜ 置信度：{conf}")
        out.append("")
        return out

    lines.append("## 今日必读（P0）")
    lines.append("")
    if p0:
        for it in p0:
            lines.extend(render_item(it))
    else:
        lines.append("今日无 P0 事项。")
        lines.append("")

    lines.append("## 值得讨论（P1）")
    lines.append("")
    if p1:
        for it in p1:
            lines.extend(render_item(it))
    else:
        lines.append("今日无 P1 事项。")
        lines.append("")

    if p2:
        lines.append("## 今日速览（P2）")
        lines.append("")
        lines.append("| 级别 | 标题 | 一句话 | 来源 |")
        lines.append("|---|---|---|---|")
        for it in p2:
            title = str(it.get("headline", "")).replace("|", "/")
            one = str(it.get("one_liner", "")).replace("|", "/")
            link = it.get("source_link", "#")
            lines.append(f"| P2 | {title} | {one} | [链接]({link}) |")
        lines.append("")

    if dropped:
        reasons = Counter(str(d.get("reason", "未说明")).split("，")[0] for d in dropped)
        lines.append("## 今日筛掉了什么")
        lines.append("")
        lines.append(f"共 {len(dropped)} 条未进入日报：")
        lines.append("")
        for reason, cnt in reasons.most_common():
            lines.append(f"- {reason}：{cnt} 条")
        lines.append("")

    unverified = [i for i in kept if (i.get("confidence") or 0) < 0.6]
    if unverified:
        lines.append("## 待核实")
        lines.append("")
        for it in unverified:
            lines.append(f"- {it.get('headline','')}（置信度 {it.get('confidence')}）[来源]({it.get('source_link','#')})")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    src = ROOT / "data" / "items" / f"{args.date}.json"
    if not src.exists():
        print(f"[error] 找不到 {src}，先跑 extract.py", file=sys.stderr)
        sys.exit(1)
    items = json.loads(src.read_text(encoding="utf-8"))
    md = render(items)

    out_file = Path(args.out) if args.out else ROOT / "output" / f"daily-{args.date}.md"
    if not out_file.is_absolute():
        out_file = ROOT / out_file
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(md, encoding="utf-8")
    print(f"[done] 日报已生成 -> {out_file.relative_to(ROOT)}（{len(md)} 字符）")


if __name__ == "__main__":
    main()
