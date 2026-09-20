#!/usr/bin/env python3
"""跨天去重：维护最近 N 条 URL 的滑动窗口。

背景（真实踩坑）：跨天推送时旧推文重复出现。修复方式是在采集阶段就按 URL 跳过，
而不是在生成阶段才去重——后者的代价是报告已经生成，重跑成本高。
"""
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

WINDOW = 5000


def seen_path(root: Path, filename: str = "seen_urls.json") -> Path:
    # demo 模式用独立文件，否则样例数据被记住后第二次演示会全部跳过
    return Path(root) / "data" / filename


def load_seen(root: Path, window: int = WINDOW, filename: str = "seen_urls.json") -> set:
    p = seen_path(root, filename)
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return set()
    urls = data.get("urls", []) if isinstance(data, dict) else data
    return set(urls[-window:])


def save_seen(root: Path, urls: set, window: int = WINDOW, filename: str = "seen_urls.json") -> int:
    p = seen_path(root, filename)
    p.parent.mkdir(parents=True, exist_ok=True)
    merged = sorted(urls)[-window:]
    p.write_text(json.dumps({"count": len(merged), "urls": merged},
                            ensure_ascii=False, indent=2), encoding="utf-8")
    return len(merged)


def filter_new(items, seen: set):
    """返回 (新条目, 被跳过的数量)，并把新 URL 写回 seen 集合（原地修改）。"""
    fresh, skipped = [], 0
    for it in items:
        url = (it.get("link") or it.get("url") or "").strip()
        if url and url in seen:
            skipped += 1
            continue
        if url:
            seen.add(url)
        fresh.append(it)
    return fresh, skipped


if __name__ == "__main__":
    # 自测：模拟两天的采集，第二天同一条 URL 应被跳过
    root = Path(__file__).resolve().parents[1]
    seen = load_seen(root)
    day1 = [{"link": "https://example.com/a"}, {"link": "https://example.com/b"}]
    fresh, skipped = filter_new(day1, seen)
    print(f"第一天：新增 {len(fresh)}，跳过 {skipped}")
    day2 = [{"link": "https://example.com/a"}, {"link": "https://example.com/c"}]
    fresh2, skipped2 = filter_new(day2, seen)
    print(f"第二天：新增 {len(fresh2)}，跳过 {skipped2}（应为 1）")
    save_seen(root, seen)
    print("去重库已写入 data/seen_urls.json")
