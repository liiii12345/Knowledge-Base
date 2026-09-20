#!/usr/bin/env python3
"""质量红线检查：把"报告标准"变成可执行、可测试的关卡。

五条红线（对应 docs/daily-report-spec.md）：
  R1 每条必须有中文摘要，推文 30-80 字
  R2 每条必须标注来源账号 / 频道
  R3 每条必须有可点击链接
  R4 禁止主观推断句式（这意味着 / 预示着 / 标志着 / 我们有理由相信）
  R5 YouTube 条目必须包含 主题 + 嘉宾 + 核心内容 三要素

设计原则：**写 prompt 要求模型遵守是不够的**——必须有一层代码兜底，
模型偶尔违反时把条目挡在正文之外，而不是让不合格内容流到读者面前。
"""
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FORBIDDEN = ["这意味着", "预示着", "标志着", "我们有理由相信", "毫无疑问", "必将"]
CN_RE = re.compile(r"[\u4e00-\u9fff]")


def cn_len(text: str) -> int:
    """中文摘要按汉字计数，忽略标点与英文单词长度带来的误差。"""
    return len(CN_RE.findall(text or ""))


def check_item(item: dict) -> list:
    """返回违反的红线编号列表，空列表表示全部通过。"""
    violations = []
    platform = item.get("platform", "twitter")
    summary = (item.get("summary") or "").strip()

    # R1 中文摘要长度：推文 30-80 汉字，YouTube 正文摘要不少于 20 汉字
    if platform == "twitter":
        n = cn_len(summary)
        if n < 30 or n > 80:
            violations.append("R1")
    else:
        if cn_len(summary) < 20:
            violations.append("R1")

    # R2 来源标注
    if not (item.get("author") or item.get("channel") or item.get("handle")):
        violations.append("R2")

    # R3 可点击链接
    link = (item.get("link") or "").strip()
    if not (link.startswith("http://") or link.startswith("https://")):
        violations.append("R3")

    # R4 主观推断句式
    blob = f"{item.get('title','')} {summary}"
    if any(p in blob for p in FORBIDDEN):
        violations.append("R4")

    # R5 YouTube 三要素：标题(主题) + author(嘉宾/频道) + summary(核心内容)
    if platform == "youtube":
        if not item.get("title") or not item.get("author") or not summary:
            violations.append("R5")

    return sorted(set(violations))


def check_items(items: list) -> tuple:
    passed, failed = [], []
    for it in items:
        v = check_item(it)
        if v:
            failed.append({"item": it, "violations": v})
        else:
            passed.append(it)
    return passed, failed


def report_lines(failed: list) -> list:
    lines = []
    for f in failed:
        title = f["item"].get("title", "")[:30]
        lines.append(f"- [{','.join(f['violations'])}] {title}")
    return lines


VIOLATION_TEXT = {
    "R1": "中文摘要长度不达标",
    "R2": "缺少来源标注",
    "R3": "缺少可点击链接",
    "R4": "含主观推断句式",
    "R5": "YouTube 缺主题/嘉宾/核心内容之一",
}


if __name__ == "__main__":
    items = [
        {"platform": "twitter", "author": "A", "handle": "@a", "title": "t",
         "summary": "短摘要不足三十字", "link": "https://x.com/a/1"},
        {"platform": "twitter", "author": "B", "handle": "@b", "title": "t",
         "summary": "这条推文讨论了评测集污染的实际情况，并给出了自建私有评测集的具体做法与复现步骤，建议团队尽快落地。",
         "link": "https://x.com/b/2"},
    ]
    passed, failed = check_items(items)
    print(f"通过 {len(passed)} 条，拦截 {len(failed)} 条")
    for line in report_lines(failed):
        print(line)
