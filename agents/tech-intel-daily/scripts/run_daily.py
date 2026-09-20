#!/usr/bin/env python3
"""一键跑通：采集 → 新数据验证 → 生成日报 → 编码守卫 → (可选) 发布到飞书。

任何一步失败立即发送错误通知并终止 —— 绝不推送旧内容。

    python -m scripts.run_daily --demo                  # 离线跑通，输出 data/reports/
    python -m scripts.run_daily                          # 真实采集
    python -m scripts.run_daily --publish                # 采集 + 生成 + 推送飞书
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors.collect_all import load_yaml, demo_items
from collectors.seen_urls import load_seen, save_seen, filter_new
from analysis.validate_freshness import FreshnessError, validate
from analysis.generate_report import load_raw, check_items, compose_markdown, yesterday_counts
from analysis import quality_gate

ROOT = Path(__file__).resolve().parents[1]
CN = timezone(timedelta(hours=8))


def step(name: str):
    print(f"\n=== {name} ===")


def run_day(date_str: str, cfg: dict, demo: bool, publish: bool, use_llm: bool):
    step(f"1/5 采集 · {date_str}")
    out_dir = ROOT / "data" / "raw" / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    if demo:
        # demo 模式每次从空的去重库开始（直接覆盖写入），保证可反复演示
        raw = demo_items(date_str)
        seen = set()
        raw["youtube"], s1 = filter_new(raw["youtube"], seen)
        raw["twitter"], s2 = filter_new(raw["twitter"], seen)
        save_seen(ROOT, seen, filename="seen_urls_demo.json")
        if s1 or s2:
            print(f"[info] demo 模式下跳过 {s1 + s2} 条重复 URL（清理 data/seen_urls.json 可重置）")
        (out_dir / "youtube.json").write_text(json.dumps(raw["youtube"], ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / "twitter.json").write_text(json.dumps(raw["twitter"], ensure_ascii=False, indent=2), encoding="utf-8")
        summary = {"date": date_str, "collected_at": datetime.now(CN).isoformat(),
                   "youtube_count": len(raw["youtube"]), "twitter_count": len(raw["twitter"]),
                   "total_items": len(raw["youtube"]) + len(raw["twitter"])}
        (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        import subprocess
        r = subprocess.run([sys.executable, "-m", "collectors.collect_all", "--date", date_str,
                            "--config", str(cfg.get("__path__", ROOT / "config.example.yaml"))], cwd=str(ROOT))
        if r.returncode != 0:
            raise FreshnessError("采集阶段失败")

    step("2/5 新数据验证")
    try:
        validate(date_str, min_items=1)
    except FreshnessError as exc:
        from publisher.notify import notify_error
        notify_error(cfg.get("feishu", {}).get("app_id", ""), cfg.get("feishu", {}).get("app_secret", ""),
                     cfg.get("feishu", {}).get("chat_id", ""), "新数据验证", str(exc), dry_run=not publish)
        raise SystemExit(2)

    step("3/5 质量红线 + 生成日报")
    raw = load_raw(date_str)
    passed, failed = check_items(raw["youtube"] + raw["twitter"])
    yt = [i for i in passed if i.get("platform") == "youtube"]
    tw = [i for i in passed if i.get("platform") == "twitter"]
    print(f"[ok] 红线通过 {len(passed)} / 拦截 {len(failed)}")
    prev = yesterday_counts(date_str)
    md = compose_markdown(date_str, yt, tw, failed, prev)
    if use_llm:
        print("[info] LLM 模式请在 analysis.generate_report 中单独调用（--llm）")

    step("4/5 编码守卫")
    import subprocess
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_encoding.py")], cwd=str(ROOT))
    if r.returncode != 0:
        raise FreshnessError("编码守卫未通过，终止发布")

    reports = ROOT / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    out = reports / f"{date_str}.md"
    out.write_text(md, encoding="utf-8")
    print(f"[done] 日报 -> {out.relative_to(ROOT)}（{len(md)} 字符）")

    step("5/5 发布")
    if not publish:
        print("[skip] 未开启 --publish，本地生成完成")
        return out
    feishu = cfg.get("feishu", {})
    if not feishu.get("enabled"):
        print("[skip] config 中 feishu.enabled = false")
        return out
    from publisher.feishu_client import get_tenant_token, clear_body, append_blocks, set_public
    from publisher.publish import markdown_to_blocks
    from publisher.notify import notify_success
    token = get_tenant_token(feishu["app_id"], feishu["app_secret"])
    doc = feishu["document_token"]
    blocks = markdown_to_blocks(md)
    clear_body(token, doc)
    written = append_blocks(token, doc, blocks)
    set_public(token, doc)
    print(f"[ok] 已写入 {written} 个 block")
    notify_success(feishu["app_id"], feishu["app_secret"], feishu["chat_id"], date_str, md)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(CN).strftime("%Y-%m-%d"))
    ap.add_argument("--config", default=str(ROOT / "config.example.yaml"))
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--llm", action="store_true")
    args = ap.parse_args()

    cfg_path = Path(args.config)
    cfg = load_yaml(cfg_path)
    cfg["__path__"] = str(cfg_path)
    print(f"科技情报日报 · {args.date} ｜ demo={args.demo} publish={args.publish}")
    try:
        run_day(args.date, cfg, args.demo, args.publish, args.llm)
    except FreshnessError as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
