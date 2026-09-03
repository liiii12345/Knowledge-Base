#!/usr/bin/env python3
"""抽取：对原始条目做初筛与结构化，输出结构化条目 JSON。

两种模式：
  1) LLM 模式（设置环境变量 OPENAI_API_KEY）：调用 OpenAI 兼容接口，prompt 见 prompts/
  2) 规则模式（默认）：本地启发式打分，零依赖、零成本，用于跑通流程与自测

用法：
    python scripts/extract.py --date 2026-09-03
    OPENAI_API_KEY=sk-xxx python scripts/extract.py --date 2026-09-03 --llm
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "prompts"

TOPIC_RULES = [
    ("ai-model", ["模型", "大模型", "LLM", "发布", "评测", "token", "微调", "训练"]),
    ("ai-infra", ["向量", "检索", "推理", "部署", "GPU", "调度", "数据库", "缓存"]),
    ("ai-app", ["Agent", "助手", "助手", "Copilot", "应用", "产品", "工作流"]),
    ("dev-tool", ["框架", "SDK", "开源", "库", "工具链", "CI", "编译"]),
    ("industry", ["融资", "收购", "财报", "监管", "政策", "市场"]),
]

HYPE_WORDS = ["革命性", "颠覆", "划时代", "重磅", "史诗级", "彻底改变", "重新定义", "碾压"]
SUBSTANCE_WORDS = ["评测", "参数", "定价", "价格", "开源", "复现", "脚本", "数据", "漏洞", "补丁", "上线", "发布"]
P0_WORDS = ["漏洞", "补丁", "安全", "定价", "下线", "停服", "涨价", "降级"]
WATCH_HINTS = ["融资", "财报", "传闻", "据说"]


def load_prompt(name: str) -> str:
    p = PROMPTS / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def guess_topic(text: str) -> str:
    best, hits = "industry", 0
    for topic, kws in TOPIC_RULES:
        n = sum(1 for k in kws if k in text)
        if n > hits:
            best, hits = topic, n
    return best


def effective_substance(text: str):
    """实质词要排除被否定语境覆盖的部分。

    反例："新闻稿未给出任何参数、价格或上线时间" —— 参数/价格/上线 都是实质词，
    但前面有「未给出」，实际含义是"什么都没说"。不处理这条，营销稿会混进日报。
    """
    cues = ["未给出", "未披露", "未提供", "没有提供", "暂无", "尚未", "未公开", "不含"]
    cut = len(text)
    for cue in cues:
        pos = text.find(cue)
        if pos != -1:
            cut = min(cut, pos)
    words = [w for w in SUBSTANCE_WORDS if 0 <= text.find(w) < cut]
    negated = len([w for w in SUBSTANCE_WORDS if text.find(w) >= cut and w in text])
    return words, negated


def rule_extract(entries):
    """规则模式：可解释、可复现，输出结构与 LLM 模式一致。"""
    kept, dropped = [], []
    for e in entries:
        text = f"{e.get('title','')} {e.get('summary','')}"
        hype = [w for w in HYPE_WORDS if w in text]
        substance, negated = effective_substance(text)
        has_number = bool(re.search(r"\d+(\.\d+)?%?|\d+\s*(美元|元|亿|万)", text))

        # 宣传用语 + 没有量化信息 = 营销稿。这条要先判，否则会被实质词蒙混过关
        if hype and not has_number:
            dropped.append({"title": e.get("title", ""), "reason": "含宣传用语且无量化信息"})
            continue
        if not substance and not has_number:
            dropped.append({"title": e.get("title", ""), "reason": "无可验证事实增量"})
            continue
        if negated >= 2 and len(substance) == 0:
            dropped.append({"title": e.get("title", ""), "reason": "实质信息均被否定表述覆盖"})
            continue

        priority = "P0" if any(w in text for w in P0_WORDS) else ("P1" if len(substance) >= 2 or has_number else "P2")
        impact = "me" if priority == "P0" else ("team" if priority == "P1" else "watch")
        confidence = 0.9 if has_number and substance else (0.7 if substance else 0.5)
        if any(w in text for w in WATCH_HINTS):
            confidence = min(confidence, 0.55)

        kept.append({
            "headline": (e.get("title", "")[:38] or "无标题"),
            "one_liner": (e.get("summary", "")[:60] or "原文未提供摘要"),
            "why_it_matters": "命中实质信息：" + "、".join(substance[:3]) if substance else "有量化信息，影响待评估",
            "impact": impact,
            "priority": priority,
            "confidence": confidence,
            "action": "48 小时内评估影响" if priority == "P0" else ("本周内讨论" if priority == "P1" else ""),
            "source_link": e.get("link", ""),
            "source": e.get("source", ""),
            "topic": guess_topic(text),
        })
    return kept, dropped


def call_llm(system_prompt: str, user_payload: str, model: str, base_url: str, api_key: str, timeout: int = 90):
    body = json.dumps({
        "model": model,
        "temperature": 0.2,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_payload}],
    }).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def parse_json_loose(text: str):
    """模型偶尔会包一层 ```json，容错处理。"""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("响应中未找到 JSON 数组")
    return json.loads(cleaned[start:end + 1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--llm", action="store_true", help="调用大模型（需要 OPENAI_API_KEY）")
    ap.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    ap.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    args = ap.parse_args()

    raw_file = ROOT / "data" / "raw" / f"{args.date}.json"
    if not raw_file.exists():
        print(f"[error] 找不到 {raw_file}，先跑 fetch_sources.py", file=sys.stderr)
        sys.exit(1)
    raw = json.loads(raw_file.read_text(encoding="utf-8"))
    entries = raw.get("entries", [])
    if not entries:
        print("[warn] 原始条目为空")

    use_llm = args.llm and os.getenv("OPENAI_API_KEY")
    if args.llm and not os.getenv("OPENAI_API_KEY"):
        print("[warn] 未设置 OPENAI_API_KEY，回退到规则模式")

    if use_llm:
        api_key = os.environ["OPENAI_API_KEY"]
        system = load_prompt("01-collect.md") + "\n\n---\n\n" + load_prompt("02-extract.md")
        try:
            content = call_llm(system, json.dumps(entries, ensure_ascii=False), args.model, args.base_url, api_key)
            items = parse_json_loose(content)
            kept = [i for i in items if i.get("keep", True)]
            dropped = [{"title": i.get("title", ""), "reason": i.get("reason", "")} for i in items if not i.get("keep", True)]
            print(f"[ok] LLM 模式：保留 {len(kept)} / 丢弃 {len(dropped)}")
        except Exception as exc:
            print(f"[warn] LLM 调用失败，回退规则模式：{exc}", file=sys.stderr)
            kept, dropped = rule_extract(entries)
    else:
        kept, dropped = rule_extract(entries)
        print(f"[ok] 规则模式：保留 {len(kept)} / 丢弃 {len(dropped)}")

    out_dir = ROOT / "data" / "items"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{args.date}.json"
    out_file.write_text(json.dumps(
        {"date": args.date, "mode": "llm" if use_llm else "rule",
         "kept": kept, "dropped": dropped},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] 结构化条目 -> {out_file.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
