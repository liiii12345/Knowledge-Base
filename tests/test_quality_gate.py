#!/usr/bin/env python3
"""质量红线单元测试（stdlib unittest，无需额外依赖）。

跑：python -m unittest discover tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.quality_gate import check_item, cn_len
from collectors.collect_youtube import parse_age_hours


class TestQualityGate(unittest.TestCase):

    def ok_tweet(self, **over):
        base = {"platform": "twitter", "author": "某人", "handle": "@x",
                "summary": "这是一条长度合适的中文摘要，用来验证质量红线中的字数要求是否能够被正确判定通过并返回结果。",
                "link": "https://x.com/x/status/1"}
        base.update(over)
        return base

    def test_r1_summary_too_short(self):
        self.assertIn("R1", check_item(self.ok_tweet(summary="太短了")))

    def test_r2_missing_source(self):
        self.assertIn("R2", check_item(self.ok_tweet(author="", handle="")))

    def test_r3_missing_link(self):
        self.assertIn("R3", check_item(self.ok_tweet(link="x.com/abc")))

    def test_r4_forbidden_phrase(self):
        item = self.ok_tweet()
        item["summary"] = item["summary"] + " 这意味着行业格局将迎来新的变化。"
        self.assertIn("R4", check_item(item))

    def test_r5_youtube_missing_guest(self):
        yt = {"platform": "youtube", "title": "主题", "author": "", "summary": "足够长的核心内容摘要" * 2,
              "link": "https://youtube.com/watch?v=1"}
        self.assertIn("R5", check_item(yt))

    def test_all_pass(self):
        self.assertEqual(check_item(self.ok_tweet()), [])

    def test_cn_len_ignores_non_chinese(self):
        self.assertEqual(cn_len("abc,.;中文"), 2)


class TestTimeParsing(unittest.TestCase):

    def test_chinese_units(self):
        self.assertEqual(parse_age_hours("5 日前"), 120)
        self.assertEqual(parse_age_hours("2 星期前"), 336)
        self.assertEqual(parse_age_hours("3 小时前"), 3)

    def test_english_units(self):
        self.assertEqual(parse_age_hours("3 hours ago"), 3)
        self.assertEqual(parse_age_hours("45 minutes ago"), 0.75)

    def test_unknown_returns_none(self):
        """识别不出发布时间必须返回 None → 该条目被丢弃，而不是当成新内容。"""
        self.assertIsNone(parse_age_hours("unknown"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
