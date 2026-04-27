---
name: us-stock-tracker
description: 美股行情追踪 — 双数据源（新浪实时 + Yahoo v8 收盘），含大盘/板块/异动/52周位置分析。
---

# 美股行情追踪

## 快速使用

```bash
# 实时快照（新浪财经，盘中用）
python3 scripts/snapshot.py
python3 scripts/snapshot.py --tech-only

# 收盘日报（Yahoo v8，盘后用）
python3 scripts/daily_report.py
python3 scripts/daily_report.py --tech-only

# JSON 输出
python3 scripts/snapshot.py --json
python3 scripts/daily_report.py --json
```

## 依赖

核心数据结构和分析引擎从 `shared/stock_tracker_lib` 导入。趋势阈值 `DEFAULT_TREND_THRESHOLDS`（20%/7%），
市场状态含夏令时检测。

## 文件结构

```
scripts/
  common.py         # HTTP客户端、双源ticker配置(YAHOO_STOCKS_CN中文名)、数据结构、板块分组
  analysis.py       # 分析引擎 + 叙事生成（52周位置文案、原因简述、表现综述、关键动态、一句话总结）
  snapshot.py       # 新浪财经实时快照（盘中）
  daily_report.py   # Yahoo v8 收盘日报（盘后），分析师风格输出
```

## 双数据源

| 数据源 | 端点 | 用途 | 特点 |
|--------|------|------|------|
| 新浪财经 | `hq.sinajs.cn/list=` | 实时快照 | 需要 `Referer` header + 绕过代理 |
| Yahoo v8 | `query1.finance.yahoo.com/v8/finance/chart/` | 收盘日报 + 趋势分析 | 1个月 OHLC + 52周高低 + 成交量，**必须 curl subprocess 调用（Python requests 返回 403）** |

## 环境约束

```python
# 必须设置
proxies = {"http": None, "https": None}
headers = {"User-Agent": "Mozilla/5.0 ..."}

# 新浪额外需要
headers["Referer"] = "https://finance.sina.com.cn/"

# Yahoo v8: 必须用 subprocess.run(["curl", "-s", ...]) 而非 requests
# curl 正常返回 200，Python requests 被拦截 403
```

## Cron 使用

主任务直接运行脚本：
```
python3 ~/.hermes/skills/us-stock-tracker/scripts/daily_report.py
```

## 日报输出结构（分析师风格）

日报采用「叙事 + 数据」混合风格，包含以下板块：

1. **🏛 大盘概览** — 指数涨跌表 + 一句概况（`_index_narrative`）
2. **🔍 核心科技股** — 10 只重点股表，含中英文名 + 52周位置（`_display_name` / `_fifty_two_week_text`）
3. **表现综述** — 叙事段落，自动识别半导体爆发、软硬分化、AI叙事（`_overview_narrative`）
4. **🔥 科技板块异动** — 涨/跌前五，每只附带原因简述（`_reason_brief`，方向感知：利好/利空分开）
5. **📈 走势深度分析** — 精选 2-3 只最强上涨 + 2-3 只最弱下跌个股，做多维度深度拆解
6. **🧠 关键动态** — 编号叙事，覆盖史诗级异动、AI算力链、软硬分化、中概表现（`_key_dynamics`）
7. **📈 一句话总结** — 全篇收束（`_one_line_summary`）

## 市场休市检测

`daily_report.py` 内置休市检测，判断「昨晚（美东时间）是否交易日」而非「最新数据日期」：

| 条件 | 判定 | 说明 |
|------|------|------|
| 昨晚 = 周六/日 | **休市** | 周末，输出简化消息，不拉取数据 |
| 昨晚 = 美股节假日 | **休市** | 覆盖 2026-2027 假期 |
| 昨晚 = 周一~周五 非假期 | **开盘** | 正常生成完整日报 |

关键洞察：北京时间早上 7:00，**昨晚 = 昨天美东日期**。
- 周一 7:00 → 昨晚美东周日 → 休市 ✅
- 周二 7:00 → 昨晚美东周一 → 开盘 ✅

**休市时**输出简化消息（仅标题 + 🏖️ 休市原因 + 交易时段），不生成完整日报，不发送旧数据。

## 投递

- **定时推送** — 每日 07:00 Telegram
- QQ/微信 deliver 管道不可用，详见 `cron-multi-platform-delivery` skill

## 分析维度

`analysis.py` 提供两层分析：
- **数据层** — 大盘定调、板块均涨跌、异动筛选（≥5%）、52周位置
- **叙事层** — 原因简述（启发式：天量成交/板块联动/逼近新高/横盘整理）、表现综述、关键动态编号、一句话总结

## 📈 走势深度分析 方法论

`_detect_trend()` 对每只有 1 个月历史数据的个股进行多日趋势检测：

| 维度 | 算法 | 输出 |
|------|------|------|
| 累积涨跌 | 区间首日收盘 → 最新收盘 | cumulative_return（%） |
| 连续方向 | 从最近一日向前数连续同向天数（>0.05% 为有效） | streak（正=连阳，负=连阴） |
| 涨跌比 | 上涨天数 / 总交易日 | up_ratio |
| 量价确认 | 近5日均量 / 全区间均量 | vol_ratio（>1.3 放量，<0.8 缩量） |

**趋势分类**（美股波动更大，阈值略高于中港股）：累积 ≥20% → 强势拉升；≥7% → 稳步上行；<7% → 温和走强。

`_deep_reason()` 综合五个维度生成归因：
1. **趋势形态** — 连阳/连阴天数判断多空力量
2. **量价关系** — 放量上涨（资金介入）vs 缩量上涨（动能衰减）vs 放量下跌（资金出逃）
3. **52周位置** — 逼近历史高点/低点的阻力与支撑判断
4. **板块联动** — 个股 vs 板块均值，判断 α（独立行情）或 β（系统性）属性
5. **龙头联动** — 半导体/AI 板块与 NVDA 等龙头的共振效应
