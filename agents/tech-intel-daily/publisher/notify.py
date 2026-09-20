#!/usr/bin/env python3
"""通知：群消息摘要 + 错误告警。

设计原则：**错误必须被看见**。
曾经 LLM 连续 5 天超时，流水线静默失败却照常推送了旧日报 —— 从那以后，
任何一步失败都要走到群里，而不是写在日志文件里等人看。
"""
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from publisher.feishu_client import get_tenant_token, send_group_message


def build_summary(date_str: str, report_md: str) -> str:
    lines = [f"科技情报日报已更新 · {date_str}", ""]
    for block in report_md.splitlines():
        if block.startswith("## 1. 今日速览"):
            idx = report_md.splitlines().index(block)
            for nxt in report_md.splitlines()[idx + 1: idx + 7]:
                if nxt.startswith("- "):
                    lines.append(nxt)
                elif nxt.startswith("##"):
                    break
            break
    lines.append("")
    lines.append("（完整内容见飞书文档）")
    return "\n".join(lines)


def notify_success(app_id: str, app_secret: str, chat_id: str, date_str: str, report_md: str):
    token = get_tenant_token(app_id, app_secret)
    send_group_message(token, chat_id, build_summary(date_str, report_md))
    print("[ok] 群消息摘要已发送")


def notify_error(app_id: str, app_secret: str, chat_id: str, stage: str, message: str,
                 dry_run: bool = False):
    """任何阶段失败都调用这里。**禁止让流水线带着旧数据继续往下走。**"""
    text = f"[日报流水线失败] 阶段：{stage}\n原因：{message}\n处理：今日日报不推送，请人工介入"
    if dry_run or not (app_id and app_secret and chat_id):
        print(f"[dry-run] {text}")
        return
    token = get_tenant_token(app_id, app_secret)
    send_group_message(token, chat_id, text)
    print("[ok] 错误通知已发送")


if __name__ == "__main__":
    md = Path(__file__).resolve().parents[1] / "examples" / "sample-report.md"
    if md.exists():
        print(build_summary("2026-09-20", md.read_text(encoding="utf-8")))
    notify_error("", "", "", "测试", "演示错误处理链路", dry_run=True)
