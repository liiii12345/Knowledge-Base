#!/usr/bin/env python3
"""一键跑通整条流水线：采集 → 抽取 → 渲染。

    python scripts/run.py --demo                # 零配置跑通（内置样例数据 + 规则抽取）
    python scripts/run.py                        # 真实抓取（需配置 sources.yaml）
    OPENAI_API_KEY=sk-xxx python scripts/run.py --demo --llm   # 用大模型做抽取
"""
import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
PY = sys.executable


def step(name, args):
    print(f"\n=== {name} ===")
    result = subprocess.run([PY, str(SCRIPTS / args[0])] + args[1:], cwd=str(ROOT))
    if result.returncode != 0:
        print(f"[error] {name} 失败，流水线中止", file=sys.stderr)
        sys.exit(result.returncode)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--demo", action="store_true", help="使用内置样例数据，不联网")
    ap.add_argument("--llm", action="store_true", help="用大模型抽取（需 OPENAI_API_KEY）")
    ap.add_argument("--config", default="sources.example.yaml")
    args = ap.parse_args()

    print(f"科技情报日报 · {args.date} ｜ 模式：{'demo' if args.demo else 'live'} / {'llm' if args.llm else 'rule'}")

    fetch_args = ["fetch_sources.py", "--date", args.date, "--config", args.config]
    if args.demo:
        fetch_args.append("--demo")
    step("1/3 采集", fetch_args)

    extract_args = ["extract.py", "--date", args.date]
    if args.llm:
        extract_args.append("--llm")
    step("2/3 抽取", extract_args)

    step("3/3 渲染", ["render_daily.py", "--date", args.date])

    out = ROOT / "output" / f"daily-{args.date}.md"
    print(f"\n完成。日报路径：{out}")


if __name__ == "__main__":
    main()
