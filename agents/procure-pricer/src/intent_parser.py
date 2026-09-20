# -*- coding: utf-8 -*-
"""
意图门控解析器（对应 Skill 的 §1.1 意图门控 + §2 分词占用）。

三情形判定：
  A. 本无该维度意图   -> 整维跳过，禁止伪造 match
  B. 有意图但分词被占用 -> 不再向下一维传递（如地名被供应商名占用 -> 不传 region）
  C. 有意图且未占用   -> 正常 match

产出 decisions 日志与调用计数，供评测与回归使用。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence

PROVINCES = [
    "北京市", "天津市", "上海市", "重庆市",
    "河北省", "山西省", "辽宁省", "吉林省", "黑龙江省", "江苏省", "浙江省", "安徽省",
    "福建省", "江西省", "山东省", "河南省", "湖北省", "湖南省", "广东省", "海南省",
    "四川省", "贵州省", "云南省", "陕西省", "甘肃省", "青海省", "台湾省", "内蒙古自治区",
    "广西壮族自治区", "西藏自治区", "宁夏回族自治区", "新疆维吾尔自治区",
    "香港特别行政区", "澳门特别行政区",
]
PROVINCE_SHORT = {
    "北京": "北京市", "天津": "天津市", "上海": "上海市", "重庆": "重庆市",
    "河北": "河北省", "山西": "山西省", "辽宁": "辽宁省", "吉林": "吉林省", "黑龙江": "黑龙江省",
    "江苏": "江苏省", "浙江": "浙江省", "安徽": "安徽省", "福建": "福建省", "江西": "江西省",
    "山东": "山东省", "河南": "河南省", "湖北": "湖北省", "湖南": "湖南省", "广东": "广东省",
    "海南": "海南省", "四川": "四川省", "贵州": "贵州省", "云南": "云南省", "陕西": "陕西省",
    "甘肃": "甘肃省", "青海": "青海省", "台湾": "台湾省", "内蒙古": "内蒙古自治区",
    "广西": "广西壮族自治区", "西藏": "西藏自治区", "宁夏": "宁夏回族自治区", "新疆": "新疆维吾尔自治区",
    "香港": "香港特别行政区", "澳门": "澳门特别行政区",
    # 简称：业务口语高频（「沪市」「粤东」等），不覆盖会漏掉地区过滤
    "沪": "上海市", "粤": "广东省", "鲁": "山东省", "苏": "江苏省", "浙": "浙江省",
    "京": "北京市", "津": "天津市", "渝": "重庆市", "豫": "河南省", "川": "四川省",
    "鄂": "湖北省", "湘": "湖南省", "闽": "福建省", "皖": "安徽省", "冀": "河北省",
    "桂": "广西壮族自治区", "赣": "江西省", "陕": "陕西省", "辽": "辽宁省",
}
NATIONWIDE = ["全国", "全中国", "全国范围内", "不限地区"]

ORG_SUFFIX = ["有限公司", "股份有限公司", "集团有限公司", "有限责任公司", "集团", "公司", "工厂", "厂"]
# 行业词：供应商全称常以「字号+行业」构成，无公司后缀时据此判定供应商意图
INDUSTRY_WORDS = ["陶瓷", "电缆", "卫浴", "五金", "纸业", "电气", "建材", "印务", "印刷", "装饰"]

STOPWORDS = [
    "什么价", "多少钱", "价格", "均价", "平均价", "采购价", "报价", "单价", "价钱", "价位",
    "查一下", "查询", "查一下价格", "询价", "帮我", "我想", "请问", "看看", "是多少", "多少",
    "的", "了", "吗", "呢", "请", "一下", "给", "我", "趋势", "变化", "情况", "分析", "对比",
]

SPEC_PATTERNS = [
    # 连字符型：A4-70g / XL-21 / HX-2201 / MS-8021 / PZ30-24位（须先于数字型，否则被截断成 70g）
    r"[A-Za-z0-9]{2,}-[A-Za-z0-9.]{1,}(?:mm²|mm|cm|m²|g|kg|位|寸|抽|层)?",
    r"[A-Za-z]{2,}\d{3,}[A-Za-z0-9]*",            # GP75153005 / M9028
    r"\d+(?:\.\d+)?\s*[*x×]\s*\d+(?:\.\d+)?\s*(?:mm|cm|m)?[²2]?",  # 3*4mm² / 800*800mm
    r"\d+\s*(?:抽|层|位|寸|g|kg|mm|cm|m²)",
]
DATE_LIKE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")

CAT_MATCH_THRESHOLD = 0.30
SUP_MATCH_THRESHOLD = 0.42   # 供应商名长、易误命中，阈值高于品类
SUPPLIER_MIN_LEN = 4


@dataclass
class ParseResult:
    filters: Dict[str, Optional[str]] = field(default_factory=dict)
    decisions: List[Dict] = field(default_factory=list)
    calls: int = 0
    raw_query: str = ""


def _strip(text: str, pieces: Sequence[str]) -> str:
    for p in pieces:
        if p:
            text = text.replace(p, "")
    return text


def extract_region(text: str) -> Optional[str]:
    if any(k in text for k in NATIONWIDE):
        return None
    for full in PROVINCES:
        if full in text:
            return full
    for short, full in PROVINCE_SHORT.items():
        if short in text:
            return full
    return None


def extract_brand(text: str, brands: Sequence[str]) -> Optional[str]:
    for b in sorted(brands, key=len, reverse=True):
        if b in text:
            return b
    return None


def extract_spec(text: str) -> Optional[str]:
    for pat in SPEC_PATTERNS:
        for m in re.finditer(pat, text):
            s = m.group(0).strip()
            if DATE_LIKE.match(s):      # 别把 2025-01-01 这类日期误当规格
                continue
            return s
    return None


def extract_date_range(text: str, today: date) -> (Optional[str], Optional[str]):
    """相对时间换算（真实环境由时间服务提供当天日期），明确日期直传。"""
    t = text
    m = re.search(r"近\s*(\d+)\s*天", t)
    if m:
        n = int(m.group(1))
        return (today - timedelta(days=n - 1)).isoformat(), today.isoformat()
    if "今天" in t:
        return today.isoformat(), today.isoformat()
    if "昨天" in t:
        d = today - timedelta(days=1)
        return d.isoformat(), today.isoformat()
    if "本周" in t:
        return (today - timedelta(days=today.weekday())).isoformat(), today.isoformat()
    if "本月" in t:
        return today.replace(day=1).isoformat(), today.isoformat()
    if "上个月" in t or "上月" in t:
        first = today.replace(day=1)
        last_prev = first - timedelta(days=1)
        return last_prev.replace(day=1).isoformat(), last_prev.isoformat()
    if "上季度" in t or "上季度" in t:
        q = (today.month - 1) // 3 + 1
        start_m = 3 * (q - 1) + 1
        if start_m < 1:
            start_m, y = 10, today.year - 1
        else:
            y = today.year
        end_d = date(y, start_m + 2, 1)
        end_prev = end_d - timedelta(days=1)
        return date(y, start_m, 1).isoformat(), end_prev.isoformat()
    if "近半年" in t or "最近半年" in t or "近六个月" in t:
        return (today - timedelta(days=182)).isoformat(), today.isoformat()
    if "近一年" in t or "近12个月" in t:
        return (today - timedelta(days=365)).isoformat(), today.isoformat()
    if "今年" in t:
        return today.replace(month=1, day=1).isoformat(), today.isoformat()
    if "去年" in t:
        return date(today.year - 1, 1, 1).isoformat(), date(today.year - 1, 12, 31).isoformat()

    m = re.search(r"(\d{4})\s*年\s*[~\-到至]\s*(\d{4})\s*年", t)
    if m:
        return f"{m.group(1)}-01-01", f"{m.group(2)}-12-31"
    m = re.search(r"(\d{4})\s*年", t)
    if m:
        return f"{m.group(1)}-01-01", f"{m.group(1)}-12-31"
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})\s*[~\-到至]\s*(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        a = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        b = f"{m.group(4)}-{int(m.group(5)):02d}-{int(m.group(6)):02d}"
        return a, b
    m = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日?\s*[到至~\-]\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?", t)
    if m:
        a = f"{today.year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
        b = f"{today.year}-{int(m.group(3)):02d}-{int(m.group(4)):02d}"
        return a, b
    return None, None


def _org_suffix_hit(text: str) -> bool:
    return any(s in text for s in ORG_SUFFIX)


def find_product_span(residue: str, categories: Sequence[str]):
    """
    在剩余片段中定位产品词跨度：取任一规范品类名的最长前缀在片段中出现者。
    返回 (片段中的产品词, 规范品类名)；未命中返回 (None, None)。
    例：'临沂市高新安泰纸业纸巾盒' -> ('纸巾盒', '纸巾盒子')
    """
    best = None
    for v in sorted(categories, key=len, reverse=True):
        for L in range(len(v), 1, -1):
            prefix = v[:L]
            if prefix in residue:
                if best is None or len(prefix) > len(best[0]):
                    best = (prefix, v)
                break
    return best if best else (None, None)


def parse_query(
    text: str,
    matchers: Dict[str, "VectorMatcher"],
    brands: Sequence[str],
    supplier_names: Sequence[str],
    today: date,
) -> ParseResult:
    res = ParseResult(raw_query=text)
    log = res.decisions

    # --- 1. 确定片段：地区 / 品牌 / 规格 / 时间 ---
    region = extract_region(text)
    log.append({"dim": "region", "gate": "A" if not region else "const",
                "reason": "全国/未提及 -> 不传 area" if not region else "省级常量映射，不调 MCP", "value": region})

    brand = extract_brand(text, brands)
    log.append({"dim": "brand", "gate": "skip", "reason": "话术直接提取，不调 MCP", "value": brand})

    spec = extract_spec(text)
    log.append({"dim": "spec", "gate": "skip", "reason": "话术直接提取，不调 MCP", "value": spec})

    d_start, d_end = extract_date_range(text, today)
    log.append({"dim": "date", "gate": "skip",
                "reason": "相对时间换算" if (d_start and not re.search(r"\d{4}", text)) else "明确日期直传",
                "value": f"{d_start}~{d_end}" if d_start else None})

    # --- 2. 剩余片段：剥掉已知维度与停用词 ---
    residue = text
    for piece in [region, brand, spec]:
        residue = _strip(residue, [piece] if piece else [])
    residue = _strip(residue, STOPWORDS)
    residue = re.sub(r"[，。、？?！!；;：:\s]+", "", residue)
    residue = re.sub(r"近?\d+\s*(天|个月|年)|今天|昨天|本周|本月|去年|今年|近半年|近一年|\d{4}年?|\d{1,2}月\d{1,2}日?", "", residue)

    # --- 3. 产品维度：门控 A（无产品词则不调 category） ---
    # 先定位产品词在剩余片段中的具体跨度，剥离后剩下的才是供应商候选；
    # 否则「厂名+产品」连写时会被整段当产品词，供应商维度丢失、wlms 也会被厂名污染。
    category = None
    material_desc = None
    span, canonical = find_product_span(residue, matchers["category"].values)
    supplier_cand = residue.replace(span, "") if span else residue

    if span:
        hits = matchers["category"].match(span, top_k=3)
        if hits and hits[0]["score"] >= CAT_MATCH_THRESHOLD:
            category = hits[0]["value"]
            log.append({"dim": "category", "gate": "C",
                        "reason": f"有产品意图，match 命中（{span} -> {category}，score={hits[0]['score']}）",
                        "value": category})
        else:
            # 品类未命中 -> 提炼物料关键词直接查（禁止 match(material)）
            material_desc = span
            log.append({"dim": "material_desc", "gate": "C",
                        "reason": "category 未命中，模型提炼关键词直传（不调 material）", "value": material_desc})
    else:
        log.append({"dim": "category", "gate": "A", "reason": "未识别出产品实体，整维跳过", "value": None})

    # --- 4. 供应商维度：门控 A/C ---
    supplier = None
    cand = supplier_cand
    has_org = _org_suffix_hit(cand)
    # 「宁长勿短」：候选片段是某供应商名的前缀/子串才算有供应商意图
    prefix_hit = any(len(cand) >= SUPPLIER_MIN_LEN and cand in s for s in supplier_names)
    industry_hit = any(k in cand for k in INDUSTRY_WORDS) and len(cand) >= SUPPLIER_MIN_LEN + 2
    if has_org or prefix_hit or industry_hit:
        hits = [h for h in matchers["supplier"].match(cand, top_k=3)
                if h["score"] >= SUP_MATCH_THRESHOLD]
        if hits:
            supplier = hits[0]["value"]
            log.append({"dim": "supplier", "gate": "C",
                        "reason": "有组织主体/厂名字段，match 命中", "value": supplier})
        else:
            log.append({"dim": "supplier", "gate": "C",
                        "reason": "有意图但知识库 0 候选 -> 终态未匹配，不传 filter", "value": None})
    else:
        log.append({"dim": "supplier", "gate": "A",
                    "reason": "话中无供应商主体，禁止伪造 match", "value": None})

    # --- 5. 情形 B：地名已被供应商名占用 -> 不再单独传 region ---
    if supplier and region and region.rstrip("省市自治区") in supplier:
        log.append({"dim": "region", "gate": "B",
                    "reason": f"地名已被供应商名「{supplier}」占用，避免重复过滤", "value": None})
        region = None

    res.filters = {
        "category": category,
        "material_desc": material_desc,
        "supplier_name": supplier,
        "brand": brand,
        "spec": spec,
        "region": region,
        "date_start": d_start,
        "date_end": d_end,
    }
    res.calls = sum(1 for d in log if d["dim"] in ("category", "material_desc", "supplier")) + (
        1 if (d_start and re.search(r"近|今天|昨天|本周|本月|今年|去年", text)) else 0)
    return res
