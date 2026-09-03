#!/usr/bin/env python3
"""采集：读取信源清单，抓取 RSS / Atom，输出原始条目 JSON。

用法：
    python scripts/fetch_sources.py                    # 真实抓取
    python scripts/fetch_sources.py --demo             # 用内置样例数据（无需联网、无需 API key）
    python scripts/fetch_sources.py --config sources.example.yaml --date 2026-09-03
"""
import argparse
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "sources.example.yaml"

UA = "tech-intel-daily/1.0 (+https://github.com/liiii12345/Knowledge-Base)"


def parse_sources(path: Path):
    """极简 YAML 解析：只支持本项目的平铺列表格式，避免引入 PyYAML 依赖。

    支持格式：
        sources:
          - name: 某科技媒体
            url: https://example.com/feed
            tags: [ai, infra]
    """
    if not path.exists():
        print(f"[warn] 信源文件不存在：{path}", file=sys.stderr)
        return []
    items, current = [], None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#") or line.strip().startswith("sources:"):
            continue
        stripped = line.strip()
        if stripped.startswith("- name:"):
            current = {"name": stripped.split(":", 1)[1].strip(), "url": "", "tags": []}
            items.append(current)
        elif ":" in stripped and current is not None:
            key, val = stripped.split(":", 1)
            key, val = key.strip(), val.strip()
            if key == "url":
                current["url"] = val
            elif key == "tags":
                current["tags"] = [t.strip() for t in val.strip("[]").split(",") if t.strip()]
    return items


def fetch(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def parse_feed(xml_text: str, source_name: str):
    """同时兼容 RSS 2.0 与 Atom。"""
    entries = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        print(f"[warn] {source_name} 解析失败：{exc}", file=sys.stderr)
        return entries

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    nodes = root.findall(".//item") or root.findall(".//atom:entry", ns)
    for node in nodes[:30]:
        def pick(*tags):
            for t in tags:
                el = node.find(t) if not t.startswith("atom:") else node.find(t, ns)
                if el is not None:
                    if t == "atom:link":
                        return el.get("href", "")
                    return (el.text or "").strip()
            return ""
        title = pick("title", "atom:title")
        link = pick("link", "atom:link")
        summary = pick("description", "summary", "atom:summary")
        published = pick("pubDate", "updated", "atom:updated", "published")
        if title:
            entries.append({
                "title": title,
                "link": link,
                "summary": (summary or "")[:600],
                "source": source_name,
                "published": published,
            })
    return entries


DEMO_ENTRIES = [
    {"title": "开源模型发布新版，代码任务评测提升 12%，定价下调至每百万 token 3 美元",
     "link": "https://example.com/a", "summary": "官方公布评测数据与新定价，即日生效。",
     "source": "示例信源 A", "published": "2026-09-03"},
    {"title": "向量数据库新增混合检索能力，支持稀疏与稠密向量联合排序",
     "link": "https://example.com/b", "summary": "官方博客介绍了实现细节与召回评测结果。",
     "source": "示例信源 B", "published": "2026-09-03"},
    {"title": "某公司宣称推出革命性平台，将彻底改变行业格局",
     "link": "https://example.com/c", "summary": "新闻稿未给出任何参数、价格或上线时间。",
     "source": "示例信源 C", "published": "2026-09-03"},
    {"title": "主流框架发布安全补丁，修复一个高危反序列化漏洞",
     "link": "https://example.com/d", "summary": "建议所有使用者在 48 小时内升级到补丁版本。",
     "source": "示例信源 D", "published": "2026-09-03"},
    {"title": "一篇关于 Agent 记忆机制的长文，对比了五种上下文压缩方案并给出评测脚本",
     "link": "https://example.com/e", "summary": "作者开源了复现脚本与测试集。",
     "source": "示例信源 E", "published": "2026-09-03"},
    {"title": "融资快讯：某 AI 初创完成 B 轮融资",
     "link": "https://example.com/f", "summary": "金额未披露，投资方未披露。",
     "source": "示例信源 F", "published": "2026-09-03"},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--demo", action="store_true", help="使用内置样例数据，不联网")
    ap.add_argument("--lookback-days", type=int, default=2, help="只保留最近 N 天发布的条目")
    args = ap.parse_args()

    if args.demo:
        entries = DEMO_ENTRIES
    else:
        sources = parse_sources(Path(args.config))
        if not sources:
            print("[error] 没有可用信源。复制 sources.example.yaml 为 sources.yaml 并填写，或加 --demo", file=sys.stderr)
            sys.exit(1)
        entries = []
        for s in sources:
            try:
                xml_text = fetch(s["url"])
                got = parse_feed(xml_text, s["name"])
                for g in got:
                    g["tags"] = s.get("tags", [])
                entries.extend(got)
                print(f"[ok] {s['name']}: {len(got)} 条")
            except Exception as exc:
                print(f"[warn] {s['name']} 抓取失败：{exc}", file=sys.stderr)

    out_dir = ROOT / "data" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{args.date}.json"
    payload = {"date": args.date, "collected_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
               "count": len(entries), "entries": entries}
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] 原始条目 {len(entries)} 条 -> {out_file.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
