#!/usr/bin/env python3
"""新数据验证：没有今日新数据就立刻失败，宁可不发，也不发昨天的旧内容。

真实事故：LLM 连续 5 天调用超时，定时任务仍照常推送了 7/24 的旧日报，
订阅者误以为是当日情报。修复后把"验证"固化为流水线的第 3 步硬性关卡。
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
CN = timezone(timedelta(hours=8))


class FreshnessError(Exception):
    pass


def validate(date_str: str = "", min_items: int = 1) -> dict:
    """检查 data/raw/<date>/ 是否存在且条目数达标。

    不传日期时默认今天。抛 FreshnessError 表示不可继续。
    """
    date_str = date_str or datetime.now(CN).strftime("%Y-%m-%d")
    day_dir = ROOT / "data" / "raw" / date_str
    if not day_dir.exists():
        raise FreshnessError(f"今日目录不存在：data/raw/{date_str} —— 采集阶段未产出数据")

    summary_file = day_dir / "summary.json"
    if not summary_file.exists():
        raise FreshnessError(f"缺少 summary.json：{summary_file}")

    summary = json.loads(summary_file.read_text(encoding="utf-8-sig"))
    total = int(summary.get("total_items", 0))
    if total < min_items:
        raise FreshnessError(f"今日条目数不足：{total} < {min_items}")

    collected = summary.get("collected_at", "")
    if collected:
        try:
            t = datetime.fromisoformat(collected)
            age_h = (datetime.now(CN) - t).total_seconds() / 3600
            if age_h > 24:
                raise FreshnessError(f"数据过期 {age_h:.1f}h：疑似旧数据，拒绝继续")
        except ValueError:
            pass

    print(f"[ok] 新数据验证通过：{date_str} 共 {total} 条")
    return summary


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="")
    ap.add_argument("--min-items", type=int, default=1)
    args = ap.parse_args()
    try:
        validate(args.date, args.min_items)
    except FreshnessError as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        print("[action] 请发送错误通知到群，禁止推送旧日报", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
