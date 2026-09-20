# -*- coding: utf-8 -*-
"""
模拟规范值召回接口（term.match）：把用户口语词模糊召回为知识库规范值。

真实环境是向量检索；这里用「字符 bigram + 余弦相似度」复刻其行为，
保留两个关键特性：
  1. 传入词与返回词允许不完全一致（纸巾盒 -> 纸巾盒子）
  2. 召回结果按相似度排序，由模型结合意图择一
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Sequence


def _bigrams(text: str) -> Counter:
    s = re.sub(r"\s+", "", text)
    if len(s) < 2:
        return Counter([s]) if s else Counter()
    return Counter(s[i:i + 2] for i in range(len(s) - 1))


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    num = sum(a[k] * b[k] for k in common)
    den = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return num / den if den else 0.0


class VectorMatcher:
    """对一组规范值做模糊召回，等价于知识库候选匹配。"""

    def __init__(self, dimension: str, values: Sequence[str]):
        self.dimension = dimension
        self.values = list(dict.fromkeys(values))
        self._vecs = {v: _bigrams(v) for v in self.values}

    def match(self, content: str, top_k: int = 5, threshold: float = 0.18) -> List[Dict]:
        q = _bigrams(content)
        scored = [(v, _cosine(q, self._vecs[v])) for v in self.values]
        scored.sort(key=lambda x: (-x[1], len(x[0])))
        hits = [{"value": v, "score": round(s, 4)} for v, s in scored if s >= threshold]
        return hits[:top_k]


def build_matchers(rows: Sequence[Dict]) -> Dict[str, VectorMatcher]:
    """从价格库抽出各维度的规范值集合，构建候选匹配器。"""
    return {
        "category": VectorMatcher("category", [r["category"] for r in rows]),
        "supplier": VectorMatcher("supplier", [r["supplier_name"] for r in rows]),
        "brand": VectorMatcher("brand", [r["brand"] for r in rows]),
    }
