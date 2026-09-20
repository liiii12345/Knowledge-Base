#!/usr/bin/env python3
"""Twitter/X 采集：走 Nitter RSS 镜像。

真实踩坑：
1. Nitter 返回空内容 —— 必须带浏览器 User-Agent，否则被拦
2. 多实例轮询反而不稳定 —— 单一实例 + 失败即降级比重试更快得到结果
"""
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def fetch_rss(instance: str, handle: str, proxy: str = "", timeout: int = 20) -> str:
    url = f"{instance.rstrip('/')}/{handle.lstrip('@')}/rss"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml"})
    opener = urllib.request.build_opener()
    if proxy:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"https": proxy, "http": proxy}))
    with opener.open(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def parse_rfc822(text: str):
    # Nitter 返回 RFC 822：Mon, 02 Jan 2006 15:04:05 GMT
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            dt = datetime.strptime(text.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def collect_account(account: dict, instances: list, lookback_hours: int = 24,
                    limit: int = 20, proxy: str = "") -> list:
    last_err = None
    for instance in instances:
        try:
            xml_text = fetch_rss(instance, account["handle"], proxy)
            break
        except Exception as exc:
            last_err = exc
            continue
    else:
        print(f"[warn] Twitter {account['name']} 全部实例失败：{last_err}", file=sys.stderr)
        return []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        print(f"[warn] Twitter {account['name']} RSS 解析失败：{exc}", file=sys.stderr)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    items = []
    for node in root.findall(".//item")[:limit]:
        def pick(tag):
            el = node.find(tag)
            return (el.text or "").strip() if el is not None else ""
        pub = parse_rfc822(pick("pubDate"))
        if pub is None or pub < cutoff:
            continue
        link = pick("link")
        title = pick("title")
        if not link:
            continue
        # Nitter 的 title 常带 "RT by ..." 前缀，去掉以免污染摘要
        body = pick("description") or title
        items.append({
            "platform": "twitter",
            "author": account["name"],
            "handle": account["handle"],
            "domain": account.get("domain", ""),
            "title": title[:120],
            "summary": body,
            "link": link,
            "published": pub.astimezone(timezone(timedelta(hours=8))).isoformat(),
            "age_hours": (datetime.now(timezone.utc) - pub).total_seconds() / 3600,
        })
    return items


def collect_all(accounts: list, instances: list, lookback_hours: int = 24,
                limit: int = 20, proxy: str = "") -> list:
    all_items = []
    for acc in accounts:
        got = collect_account(acc, instances, lookback_hours, limit, proxy)
        print(f"[ok] Twitter {acc['name']}: {len(got)} 条（{lookback_hours}h 内）")
        all_items.extend(got)
    return all_items
