# -*- coding: utf-8 -*-
"""
生成脱敏的采购价格库样本数据。

数据全部虚构，不来自任何真实企业系统，仅用于演示与评测检索链路。
运行：python src/generate_mock_data.py
输出：data/price_library.csv

设计要点：
  - category（分类）取物料名，与真实价格库「分类」口径一致：用户说「抛釉砖」即命中分类
  - material_desc（物料描述）为「分类 + 规格 + 品牌」的长文本，用于验证
    「其他 filter 已足够时不再传物料描述，避免包含匹配把噪声带进来」这一规则
  - 供应商与地区做关联分布，避免均匀分布导致多维过滤必然空结果
"""
import csv
import os
import random
from datetime import date, timedelta

random.seed(20260903)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "price_library.csv")

# 品类大类 -> 分类（物料名）
CATEGORY_GROUPS = {
    "建筑陶瓷": ["抛釉砖", "抛光砖", "仿古砖", "通体大理石瓷砖", "内墙釉面砖"],
    "电线电缆": ["铜芯电力电缆", "铝合金电缆", "控制电缆", "阻燃交联电缆"],
    "卫生洁具": ["面盆龙头", "淋浴花洒", "连体坐便器", "浴室柜"],
    "五金配件": ["液压铰链", "不锈钢合页", "静音滑轨", "执手门锁"],
    "纸品耗材": ["纸巾盒子", "擦手纸", "复印纸", "垃圾袋"],
    "配电设备": ["低压配电箱", "动力配电箱", "照明配电箱"],
}

BASE_PRICE = {
    "抛釉砖": 62.0, "抛光砖": 48.0, "仿古砖": 71.0, "通体大理石瓷砖": 118.0, "内墙釉面砖": 33.0,
    "铜芯电力电缆": 26.5, "铝合金电缆": 15.8, "控制电缆": 9.4, "阻燃交联电缆": 31.2,
    "面盆龙头": 268.0, "淋浴花洒": 392.0, "连体坐便器": 640.0, "浴室柜": 1180.0,
    "液压铰链": 4.2, "不锈钢合页": 7.6, "静音滑轨": 12.3, "执手门锁": 86.0,
    "纸巾盒子": 6.8, "擦手纸": 4.1, "复印纸": 22.5, "垃圾袋": 1.9,
    "低压配电箱": 860.0, "动力配电箱": 1420.0, "照明配电箱": 520.0,
}

SPEC_TEMPLATE = {
    "建筑陶瓷": ["800*800mm", "600*600mm", "750*1500mm", "300*600mm"],
    "电线电缆": ["3*4mm²", "4*16mm²", "5*10mm²", "2*2.5mm²"],
    "卫生洁具": ["GP75153005", "HX-2201", "M9028", "AM-1180"],
    "五金配件": ["HY-35", "304-4寸", "SL-450", "MS-8021"],
    "纸品耗材": ["200抽", "3层*120抽", "A4-70g", "45*50cm"],
    "配电设备": ["XL-21", "GGD-380V", "PZ30-24位"],
}

GROUP_BRANDS = {
    "建筑陶瓷": ["东鹏", "马可波罗", "蒙娜丽莎"],
    "电线电缆": ["远东", "正泰", "公牛"],
    "卫生洁具": ["惠达", "箭牌", "九牧"],
    "五金配件": ["名门", "顶固", "百隆"],
    "纸品耗材": ["维达", "心相印", "洁云"],
    "配电设备": ["正泰", "德力西", "施耐德"],
}

REGIONS = [
    "北京市", "天津市", "上海市", "重庆市",
    "河北省", "山西省", "辽宁省", "吉林省", "黑龙江省", "江苏省", "浙江省", "安徽省",
    "福建省", "江西省", "山东省", "河南省", "湖北省", "湖南省", "广东省", "海南省",
    "四川省", "贵州省", "云南省", "陕西省", "甘肃省", "青海省", "台湾省", "内蒙古自治区",
    "广西壮族自治区", "西藏自治区", "宁夏回族自治区", "新疆维吾尔自治区",
    "香港特别行政区", "澳门特别行政区",
]

CITY_PREFIX = ["章丘", "佛山", "南安", "温州", "常州", "临沂", "淄博", "中山", "泉州", "宁波",
               "无锡", "绍兴", "台州", "洛阳", "衡阳", "江门", "泰州", "潍坊", "西樵", "清远"]
TRADE_NAME = ["义和", "宏发", "金鼎", "瑞丰", "华远", "恒信", "广厦", "联创", "正扬", "嘉盛",
              "德源", "天成", "兴业", "万邦", "锦程", "安泰", "永固", "盛达"]
# 供应商行业词与品类大类绑定，避免出现「纸业公司卖瓷砖」这类不合理样本
GROUP_INDUSTRY = {
    "建筑陶瓷": "陶瓷", "电线电缆": "电缆", "卫生洁具": "卫浴",
    "五金配件": "五金", "纸品耗材": "纸业", "配电设备": "电气",
}
DISTRICT = ["明水", "城东", "高新", "西城", "开发区", "工业园"]

# 高频省份：任何品类都保证覆盖，避免「山东省抛釉砖」这类常见问法落到空集
HOT_REGIONS = ["广东省", "山东省", "江苏省", "浙江省", "河南省", "四川省",
               "湖北省", "湖南省", "河北省", "福建省", "上海市", "北京市"]

REGION_FACTOR = {"广东省": 0.95, "山东省": 0.93, "江苏省": 1.02, "浙江省": 1.04,
                 "上海市": 1.12, "北京市": 1.10, "四川省": 1.01, "河南省": 0.94}
BRAND_FACTOR = {"东鹏": 1.15, "马可波罗": 1.12, "蒙娜丽莎": 1.08, "惠达": 1.05, "箭牌": 1.06,
                "九牧": 1.07, "远东": 1.11, "正泰": 1.09, "公牛": 1.14, "名门": 1.02,
                "顶固": 1.04, "百隆": 1.16, "维达": 1.10, "心相印": 1.06, "洁云": 0.98,
                "德力西": 1.08, "施耐德": 1.20}

RECORDS_PER_CELL = 60          # 每个（分类 x 地区）单元的记录数
EXTRA_REGIONS = 6              # 除高频省份外，每个品类额外覆盖的省份数
SUPPLIERS_PER_GROUP = 8


def make_supplier(n: int, industry: str):
    suppliers = set()
    while len(suppliers) < n:
        name = (f"{random.choice(CITY_PREFIX)}市{random.choice(DISTRICT)}"
                f"{random.choice(TRADE_NAME)}{industry}"
                f"{random.choice(['有限公司', '股份有限公司', '集团有限公司'])}")
        suppliers.add(name)
    return sorted(suppliers)


def main():
    supplier_pool = {
        group: make_supplier(SUPPLIERS_PER_GROUP, industry)
        for group, industry in GROUP_INDUSTRY.items()
    }
    start, end = date(2024, 1, 1), date(2026, 8, 31)
    span = (end - start).days

    rows = []
    for group, categories in CATEGORY_GROUPS.items():
        group_suppliers = supplier_pool[group]
        for cat in categories:
            # 供应商按品类切片，行业内不串货
            offset = categories.index(cat) * 2
            suppliers = [group_suppliers[(offset + i) % len(group_suppliers)] for i in range(3)]
            regions = HOT_REGIONS + random.sample(
                [r for r in REGIONS if r not in HOT_REGIONS], EXTRA_REGIONS)
            brands = GROUP_BRANDS[group]
            specs = SPEC_TEMPLATE[group]
            base = BASE_PRICE[cat]

            for region in regions:
                for _ in range(RECORDS_PER_CELL):
                    brand = random.choice(brands)
                    spec = random.choice(specs)
                    supplier = random.choice(suppliers)
                    d = start + timedelta(days=random.randint(0, span))

                    trend = 1 + (d - start).days / span * 0.08
                    noise = random.uniform(0.85, 1.18)
                    price = base * REGION_FACTOR.get(region, 1.0) * BRAND_FACTOR.get(brand, 1.0) * noise * trend

                    rows.append({
                        "record_date": d.isoformat(),
                        "category_group": group,
                        "category": cat,
                        "material_desc": f"{cat} {spec} {brand}",
                        "supplier_name": supplier,
                        "brand": brand,
                        "spec": spec,
                        "region": region,
                        "price_excl_tax": round(price, 2),
                        "price_incl_tax": round(price * 1.13, 2),
                    })

    random.shuffle(rows)
    rows.sort(key=lambda r: (r["record_date"], r["category"], r["supplier_name"]))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    size = os.path.getsize(OUT) / 1024
    print(f"已生成 {len(rows)} 条脱敏价格记录 -> {OUT}（{size:.0f} KB）")
    print(f"品类大类 {len(CATEGORY_GROUPS)} / 分类 {len(BASE_PRICE)} / "
          f"供应商 {len(set(r['supplier_name'] for r in rows))} / 地区 {len(set(r['region'] for r in rows))}")


if __name__ == "__main__":
    main()
