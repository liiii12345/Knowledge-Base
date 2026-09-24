#!/usr/bin/env python3
"""YouTube 采集：不使用 yt-dlp，直接解析页面内嵌的 ytInitialData。

为什么不用 yt-dlp：YouTube 已封禁（2026-07 起全部请求失败）。
方案改为抓取频道 Videos Tab 页面 → 正则提取 ytInitialData JSON → 解析 lockupViewModel。

两个真实坑（都已处理）：
1. Tab 标题随代理 IP 变化：英文 "Videos" / 中文 "影片" 都要匹配
2. 中文时间文案：返回 "5 日前"、"2 星期前"，不识别就会把所有老视频当成新视频
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

CN_UNIT_HOURS = {"分钟": 1 / 60, "小时": 1, "天": 24, "日": 24, "周": 168,
                 "星期": 168, "个月": 720, "月": 720, "年": 8760}
EN_UNIT_HOURS = {"second": 1 / 3600, "minute": 1 / 60, "hour": 1, "day": 24,
                 "week": 168, "month": 720, "year": 8760}


def parse_age_hours(text: str):
    """把 '5 日前' / '2 星期前' / '3 hours ago' / '10 minutes ago' 解析为小时数。

    返回 None 表示无法识别——宁可判为未知，也不要当成"刚刚发布"混进日报。
    """
    if not text:
        return None
    t = text.strip().lower()
    m = re.search(r"(\d+)\s*(分钟|小时|天|日|星期|周|个月|月|年)", t)
    if m and "前" in t:
        return int(m.group(1)) * CN_UNIT_HOURS[m.group(2)]
    m = re.search(r"(\d+)\s*(second|minute|hour|day|week|month|year)s?\s*ago", t)
    if m:
        return int(m.group(1)) * EN_UNIT_HOURS[m.group(2)]
    if "just now" in t or "刚刚" in t:
        return 0.0
    return None


def fetch_channel_page(handle: str, proxy: str = "", timeout: int = 20) -> str:
    # handle 可能写作 "@X" 或 "X"，统一成 "@X" 再拼 videos Tab
    url = f"https://www.youtube.com/@{handle.lstrip('@')}/videos"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    opener = urllib.request.build_opener()
    if proxy:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"https": proxy, "http": proxy}))
    with opener.open(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def extract_initial_data(html: str):
    m = re.search(r"var ytInitialData\s*=\s*(\{.*?\});</script>", html, re.S)
    if not m:
        m = re.search(r"ytInitialData\"\]\s*=\s*(\{.*?\});</script>", html, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def walk_videos(node, out):
    """递归找 lockupViewModel / videoRenderer，避免写死层级。"""
    if isinstance(node, dict):
        if "videoId" in node and ("title" in node or "headline" in node):
            out.append(node)
        for v in node.values():
            walk_videos(v, out)
    elif isinstance(node, list):
        for v in node:
            walk_videos(v, out)


def flatten(raw):
    def text_of(field):
        if isinstance(field, dict):
            return field.get("content") or field.get("simpleText") or ""
        if isinstance(field, list) and field:
            return text_of(field[0])
        return ""

    published = (text_of(raw.get("publishedTimeText")) or text_of(raw.get("publishedTime")))
    title = (text_of(raw.get("title")) or text_of(raw.get("headline")))
    vid = raw.get("videoId", "")
    owner = text_of(raw.get("ownerText")) or text_of(raw.get("shortBylineText"))
    length = text_of(raw.get("lengthText")) or text_of(raw.get("thumbnailOverlayTimeStatusRenderer"))
    return {
        "platform": "youtube",
        "title": title.strip(),
        "author": owner.strip(),
        "link": f"https://www.youtube.com/watch?v={vid}" if vid else "",
        "age_text": published.strip(),
        "duration": length.strip(),
        "summary": "",
        "raw_published": published.strip(),
    }


def collect_channel(channel: dict, lookback_hours: int = 24, proxy: str = "") -> list:
    try:
        html = fetch_channel_page(channel["handle"], proxy)
    except Exception as exc:
        print(f"[warn] YouTube {channel['name']} 抓取失败：{exc}", file=sys.stderr)
        return []
    data = extract_initial_data(html)
    if not data:
        print(f"[warn] YouTube {channel['name']} 未取到 ytInitialData", file=sys.stderr)
        return []
    nodes = []
    walk_videos(data, nodes)
    items, limit = [], channel.get("max_videos", 10)
    for raw in nodes:
        it = flatten(raw)
        it["channel"] = channel["name"]
        it["focus"] = channel.get("focus", "")
        age = parse_age_hours(it["age_text"])
        it["age_hours"] = age
        # 24h 过滤：无法识别发布时间的一律丢弃（宁缺勿滥）
        if age is None or age > lookback_hours:
            continue
        if not it["title"] or not it["link"]:
            continue
        items.append(it)
        if len(items) >= limit:
            break
    return items


def collect_all(channels: list, lookback_hours: int = 24, proxy: str = "") -> list:
    all_items = []
    for ch in channels:
        got = collect_channel(ch, lookback_hours, proxy)
        print(f"[ok] YouTube {ch['name']}: {len(got)} 条（{lookback_hours}h 内）")
        all_items.extend(got)
    return all_items


if __name__ == "__main__":
    # 时间解析自测：这是本项目最容易出错的一环
    cases = ["5 日前", "2 星期前", "3 hours ago", "45 minutes ago", "刚刚", "2 个月前", "unknown"]
    for c in cases:
        print(f"  {c!r:20} -> {parse_age_hours(c)} h")
