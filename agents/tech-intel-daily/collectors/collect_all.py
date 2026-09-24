#!/usr/bin/env python3
"""统一采集入口：代理检测 → YouTube + Twitter 采集 → 去重 → 写 raw 数据 → 汇总。

用法：
    python -m collectors.collect_all --date 2026-09-20
    python -m collectors.collect_all --date 2026-09-20 --demo     # 用本地样例原始数据
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors import seen_urls
from collectors.collect_youtube import collect_all as collect_yt
from collectors.collect_twitter import collect_all as collect_tw

ROOT = Path(__file__).resolve().parents[1]
CN = timezone(timedelta(hours=8))


def load_yaml(path: Path) -> dict:
    """轻量 YAML 读取：够用且不引入 PyYAML 依赖。

    真实 config.yaml 是两层缩进结构，这里支持到二级，够本项目使用。
    """
    cfg, section, key = {}, None, None
    if not path.exists():
        return cfg
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if stripped.startswith("- "):
            if key is not None:
                cfg.setdefault(f"{section}.{key}", []).append(stripped[2:].strip())
            continue
        if indent == 0 and stripped.endswith(":"):
            section, key = stripped[:-1], None
            cfg.setdefault(section, {})
        elif ":" in stripped:
            k, v = stripped.split(":", 1)
            k, v = k.strip(), v.strip()
            if indent <= 2:
                key = k
                if isinstance(cfg.get(section), dict):
                    cfg[section][k] = parse_scalar(v)
            elif key is not None and isinstance(cfg.get(section), dict):
                if isinstance(cfg[section].get(key), list):
                    cfg[section][key].append({k: parse_scalar(v)})
                else:
                    cfg[section][key] = {k: parse_scalar(v)}
    return cfg


def parse_scalar(v: str):
    if v.startswith("[") and v.endswith("]"):
        return [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
    if v.startswith('"') and v.endswith('"'):
        return v[1:-1]
    if v in ("true", "false"):
        return v == "true"
    try:
        return int(v)
    except ValueError:
        return v


def check_proxy(url: str, timeout: int = 10) -> bool:
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"https": url, "http": url}))
    try:
        with opener.open(urllib.request.Request("https://www.youtube.com", method="HEAD"), timeout=timeout):
            return True
    except Exception:
        return False


def demo_items(date_str: str):
    """离线样例数据：字段结构与线上采集产出完全一致，用于跑通整条流水线。

    重要：样例中的频道名、账号名、链接**全部虚构**，不使用任何真实人物或真实 URL。
    理由：demo 跑出来的日报会被当成样例展示，如果把虚构内容挂在真人名字下，
    等于批量生产假引用。演示归演示，不能拿真人的名义编话。

    其中一条摘要故意写短（<30 汉字），用于验证质量红线 R1 确实会拦截。
    """
    yt = [
        {"platform": "youtube", "channel": "示例播客频道 A", "author": "示例播客频道 A",
         "title": "从零搭建大模型评测流水线（示例）",
         "link": "https://example.com/watch?v=demo01", "focus": "AI 工程实践",
         "duration": "1:12:30", "age_text": "6 小时前", "age_hours": 6.0,
         "summary": "与某 AI 产品负责人对谈，主题是从零搭建大模型评测流水线，覆盖数据集构造、回归测试与线上监控三部分。"},
        {"platform": "youtube", "channel": "示例播客频道 B", "author": "示例播客频道 B",
         "title": "生产环境里的 Agent 为什么难做（示例）",
         "link": "https://example.com/watch?v=demo02", "focus": "AI 创业 / 行业趋势",
         "duration": "58:12", "age_text": "1 天前", "age_hours": 22.0,
         "summary": "两位从业者讨论 Agent 落地难的三个原因：上下文管理、工具可靠性、以及缺乏回滚机制。"},
    ]
    tw = [
        {"platform": "twitter", "author": "示例研究员甲", "handle": "@example_researcher", "domain": "模型评测",
         "title": "评测基准污染比想象中严重（示例）", "link": "https://example.com/status/demo11",
         "summary": "多个主流基准的测试集已进入训练语料，建议团队自建私有评测集并定期重跑基线。",
         "age_hours": 3.0},
        {"platform": "twitter", "author": "示例工程师乙", "handle": "@example_engineer", "domain": "运行时 / 基建",
         "title": "边缘运行时冷启动降到 40ms（示例）", "link": "https://example.com/status/demo12",
         "summary": "示例团队宣布新的边缘运行时完成优化，冷启动时间从原来的一百八十毫秒下降到四十毫秒，目前已经在生产环境对三成流量灰度验证，下周全量放开。",
         "age_hours": 5.0},
        {"platform": "twitter", "author": "示例社区运营丙", "handle": "@example_community", "domain": "开发者社区",
         "title": "社区征文：聊聊你的 Agent 失败案例（示例）", "link": "https://example.com/status/demo13",
         "summary": "示例社区正在征集生产环境中 Agent 的真实失败复盘，包括上下文溢出、工具误调用和成本失控三类典型问题，入选稿件会在社区周会上做公开分享并结集出版。",
         "age_hours": 8.0},
        {"platform": "twitter", "author": "示例产品负责人丁", "handle": "@example_pm", "domain": "Agent 产品",
         "title": "Agent 沙箱默认改为只读（示例）", "link": "https://example.com/status/demo14",
         "summary": "沙箱执行环境改为默认只读挂载，写操作需显式授权，减少误删文件的线上事故。",
         "age_hours": 11.0},
        {"platform": "twitter", "author": "示例账号戊", "handle": "@example_short", "domain": "其他",
         "title": "这条摘要故意不达标（示例）", "link": "https://example.com/status/demo15",
         "summary": "摘要太短，用于验证红线。",
         "age_hours": 2.0},
    ]
    return {"youtube": yt, "twitter": tw}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(CN).strftime("%Y-%m-%d"))
    ap.add_argument("--config", default=str(ROOT / "config.example.yaml"))
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()

    cfg = load_yaml(Path(args.config))
    proxy = ""
    if cfg.get("proxy", {}).get("enabled"):
        url = cfg["proxy"].get("url", "")
        if check_proxy(url, cfg["proxy"].get("check_timeout", 10)):
            proxy = url
            print("[ok] 代理可用")
        else:
            print("[warn] 代理不可用，直连尝试（可能失败）")

    out_dir = ROOT / "data" / "raw" / args.date
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        raw = demo_items(args.date)
    else:
        yt = collect_yt(cfg.get("youtube", {}).get("channels", []),
                        cfg.get("youtube", {}).get("lookback_hours", 24), proxy) \
            if cfg.get("youtube", {}).get("enabled") else []
        tw = collect_tw(cfg.get("twitter", {}).get("accounts", []),
                        cfg.get("twitter", {}).get("nitter_instances", ["https://nitter.net"]),
                        cfg.get("twitter", {}).get("lookback_hours", 24),
                        cfg.get("twitter", {}).get("max_tweets_per_account", 20), proxy) \
            if cfg.get("twitter", {}).get("enabled") else []
        raw = {"youtube": yt, "twitter": tw}

    seen = seen_urls.load_seen(ROOT, cfg.get("dedupe", {}).get("window_size", 5000))
    if cfg.get("dedupe", {}).get("enabled", True):
        raw["youtube"], skip_yt = seen_urls.filter_new(raw["youtube"], seen)
        raw["twitter"], skip_tw = seen_urls.filter_new(raw["twitter"], seen)
        seen_urls.save_seen(ROOT, seen, cfg.get("dedupe", {}).get("window_size", 5000))
        print(f"[ok] 去重：YouTube 跳过 {skip_yt} 条，Twitter 跳过 {skip_tw} 条")

    (out_dir / "youtube.json").write_text(
        json.dumps(raw["youtube"], ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "twitter.json").write_text(
        json.dumps(raw["twitter"], ensure_ascii=False, indent=2), encoding="utf-8")

    total = len(raw["youtube"]) + len(raw["twitter"])
    summary = {
        "date": args.date,
        "collected_at": datetime.now(CN).isoformat(),
        "youtube_count": len(raw["youtube"]),
        "twitter_count": len(raw["twitter"]),
        "total_items": total,
        "channels": cfg.get("youtube", {}).get("channels", []) or [],
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] 今日采集 {total} 条 -> data/raw/{args.date}/")


if __name__ == "__main__":
    main()
