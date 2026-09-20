# Tech Intelligence Daily Agent

一个**全自动化科技情报日报流水线**：定时采集 → 质量把关 → 生成 11 板块日报 → 双渠道推送。

不是"让 AI 帮我写个摘要"，是**把日报的判断标准固化成一整套可执行、可测试的工程**。

---

## 三分钟跑通

```bash
git clone https://github.com/liiii12345/Knowledge-Base.git
cd Knowledge-Base/agents/tech-intel-daily

python -m unittest discover -s tests     # 单元测试（10 个）
python -m scripts.run_daily --demo       # 离线跑通全流程，输出 data/reports/
```

零第三方依赖，全用 Python 标准库。`--demo` 内置虚构样例数据，不开 API key 也能出一份完整的 11 板块日报。

真实使用：

```bash
cp config.example.yaml config.yaml       # 填信源 / 飞书凭据（config.yaml 不入库）
python -m scripts.run_daily              # 采集 → 验证 → 生成
python -m scripts.run_daily --publish    # 额外推送到飞书文档 + 群消息
```

## 流水线设计（每一步都是一道关卡）

| 步骤 | 做什么 | 失败时 |
|---|---|---|
| 1 · 采集 | YouTube 频道页 + Nitter RSS，代理检测后多源并行 | 该源跳过，记日志 |
| 2 · 去重 | seen_urls 滑动窗口 5000 条，采集阶段就跳过 | — |
| 3 · **新数据验证** | 检查今日目录存在、条目 >0、数据未过期 24h | **发错误通知并终止**，禁止推旧内容 |
| 4 · 质量红线 | 五条红线逐条检查 | 违规条目挡在正文外，列进附录 |
| 5 · 生成 | 11 板块日报（LLM 模式 / 模板模式自动降级） | LLM 失败降级模板 |
| 6 · 编码守卫 | 扫描 Mojibake / `\xNN` / BOM | 终止发布 |
| 7 · 发布 | 写入飞书文档 + 群消息摘要 | 重试 + 错误通知 |

**核心原则**：自动化系统里，"没数据"必须比"推错数据"更容易被发现。

## 日报长什么样

11 个板块，顺序固定、缺失必写占位语：

```
0. 核心动态        3-5 行纯事实
1. 今日速览        3-5 条 + 热度 🔥🔥🔥
2. 今日金句        原文 + 出处 + 链接
3. 信息分层        ⚡必看 3 / 📖速读 5-10 / 🔬深读 2-3
4. YouTube 播客更新  频道|主题|嘉宾|核心内容|时长|链接
5. Twitter/X 精选  按主题分组
6. 趋势与关联      仅 ≥2 来源的共同话题
7. 行动建议        ≤3 条可执行
8. 待观察          单一来源、待交叉验证
9. 数据看板        今日 vs 昨日（无昨日数据就写"无"，不编造）
10. 推荐阅读
附录：质量红线拦截清单
```

→ [完整样例日报](examples/sample-report.md) ｜ [板块规格](docs/daily-report-spec.md)

## 五条质量红线（是代码，不是 prompt）

| 编号 | 红线 | 判定 |
|---|---|---|
| R1 | 中文摘要 | 推文 30-80 汉字；YouTube ≥20 汉字 |
| R2 | 来源标注 | author / handle / channel 至少一个 |
| R3 | 可点击链接 | 必须 http(s) 开头 |
| R4 | 无主观推断 | 禁用：这意味着、预示着、标志着、我们有理由相信、毫无疑问、必将 |
| R5 | YouTube 三要素 | 主题 + 嘉宾 + 核心内容缺一不可 |

**为什么必须是代码**：要求模型遵守 ≠ 模型一定会遵守。模型违反时，条目被 `analysis/quality_gate.py`
挡在正文之外，并在附录里写明违反原因——读者能看到"今天筛掉了什么、为什么"，而不会把不合格内容当成情报。

## 目录结构

```
agents/tech-intel-daily/
├── collectors/
│   ├── collect_youtube.py     ytInitialData 页面解析 + 中英文时间解析 + 24h 过滤
│   ├── collect_twitter.py     Nitter RSS + 浏览器 UA + 实例降级
│   ├── seen_urls.py           5000 条滑动窗口去重
│   └── collect_all.py         统一入口 + 代理检测 + 汇总
├── analysis/
│   ├── validate_freshness.py  新数据验证（禁止推旧内容）
│   ├── quality_gate.py        五条红线检查
│   └── generate_report.py     11 板块生成（LLM / 模板双模式）
├── publisher/
│   ├── feishu_client.py       token / block 写入 / 批量删除 / 权限
│   ├── publish.py             Markdown → 飞书 blocks（保留可点击链接）
│   └── notify.py              群摘要 + 错误告警
├── templates/
│   ├── analysis_prompt.md     LLM 生成 prompt（含红线与板块定义）
│   └── daily_report.md        11 板块骨架
├── docs/
│   ├── daily-report-spec.md   对外规格
│   └── engineering-notes.md   8 个真实踩坑与解法
├── scripts/
│   ├── run_daily.py           一键流水线
│   └── check_encoding.py      编码守卫
├── tests/test_quality_gate.py 10 个单元测试
└── examples/sample-report.md  样例日报
```

## 工程沉淀

8 次线上故障的完整复盘在 [`docs/engineering-notes.md`](docs/engineering-notes.md)，包括：

- **Python 3 的 `\xNN` 双重编码**：产生了 `C3 A7 C2 A7 C2 91`，飞书里全是乱码；而标题一旦写坏不可修复
- **yt-dlp 被封禁**：改用 `ytInitialData` 页面解析，递归找 `lockupViewModel`
- **中文相对时间**：`5 日前` 匹配不到英文正则，导致三天前的视频被当成今日内容
- **静默失败**：LLM 连续 5 天超时却照常推送旧日报 → 加硬性「新数据验证」关卡

每个坑都按 **现象 → 根因 → 修复 → 验证 → 预防（写成规范）** 记录，且多数已固化为可执行检查。

## 已知局限

- Twitter 依赖 Nitter 镜像，部分账号被封是三方不可控因素，只能按源跳过
- YouTube 页面解析依赖 `ytInitialData` 结构，YouTube 改版会导致解析失效
- 表格块在飞书 Markdown 转换里降级为等宽文本，未做原生表格 block
- 跨天事件聚类未实现：同一事件连续两天进入日报不会被合并
