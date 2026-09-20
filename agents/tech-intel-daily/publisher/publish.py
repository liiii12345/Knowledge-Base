#!/usr/bin/env python3
"""Markdown → 飞书 blocks 转换器。

关键点：**必须保留可点击链接**。
曾经因为一句正则 `re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1', text)` 把 URL 全丢了，
整篇日报的链接变成纯文本。修复方案是 parse_inline()：把行内 Markdown 链接
转成飞书 text_element 的 link 样式，而不是简单替换。
"""
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")

HEADING_STYLE = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6}


def parse_inline(text: str) -> list:
    """把一段文本切成飞书 text_element 数组，保留加粗与链接样式。"""
    elements, cursor = [], 0
    for m in LINK_RE.finditer(text):
        before = text[cursor:m.start()]
        elements.extend(_styled_run(before))
        url = m.group(2)
        # 飞书要求 link URL 必须转义
        elements.append({"text_run": {"content": m.group(1),
                                      "text_element_style": {"link": {"url": url.rstrip(")")}}}})
        cursor = m.end()
    tail = text[cursor:]
    elements.extend(_styled_run(tail))
    return elements or [{"text_run": {"content": "", "text_element_style": {}}}]


def _styled_run(chunk: str) -> list:
    """处理加粗：切成普通/加粗交替片段。"""
    if not chunk:
        return []
    out, cursor = [], 0
    for m in BOLD_RE.finditer(chunk):
        if m.start() > cursor:
            out.append({"text_run": {"content": chunk[cursor:m.start()], "text_element_style": {}}})
        out.append({"text_run": {"content": m.group(1),
                                 "text_element_style": {"inline_code": False, "bold": True}}})
        cursor = m.end()
    if cursor < len(chunk):
        out.append({"text_run": {"content": chunk[cursor:], "text_element_style": {}}})
    return out


def text_block(text: str, style: dict = None) -> dict:
    return {"block_type": 2, "text": {"style": style or {}, "elements": parse_inline(text)}}


def heading_block(level: int, text: str) -> dict:
    return {"block_type": 2, "heading" + str(min(level, 9)): {"style": {}, "elements": parse_inline(text)}}


def bullet_block(text: str) -> dict:
    return {"block_type": 12, "bullet": {"elements": parse_inline(text)}}


def markdown_to_blocks(md: str) -> list:
    blocks = []
    for line in md.splitlines():
        line = line.rstrip()
        if not line:
            continue
        m = re.match(r"^(#{1,9})\s+(.*)$", line)
        if m:
            blocks.append(heading_block(len(m.group(1)), m.group(2)))
        elif line.startswith("|"):
            # 表格在飞书里需要专门结构，这里降级为等宽文本块，保证信息不丢
            blocks.append(text_block(line, {"inline_code": True}))
        elif line.startswith(">"):
            blocks.append(text_block(line.lstrip("> ").strip(), {"italic": True}))
        elif line.startswith("- "):
            blocks.append(bullet_block(line[2:]))
        elif line.startswith("---"):
            continue
        else:
            blocks.append(text_block(line))
    return blocks


if __name__ == "__main__":
    sample = "这是 **加粗** 与一个 [链接](https://example.com/x) 的混合。"
    print(parse_inline(sample))
    count = len([b for b in markdown_to_blocks("# 标题\n- 条目 [A](https://a.example)\n| 1 | 2 |")])
    print(f"示例转换出 {count} 个 block")
