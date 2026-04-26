---
name: us-stock-tracker
description: 美股行情追踪 — 双数据源（新浪实时 + Yahoo v8 收盘），含大盘/板块/异动/52周位置分析。替代旧版 sina-finance-stock-data 和 us-stock-daily-report。
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
| Yahoo v8 | `query1.finance.yahoo.com/v8/finance/chart/` | 收盘日报 | 5日 OHLC + 52周高低 + 成交量，**必须 curl subprocess 调用（Python requests 返回 403）** |

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
5. **🧠 关键动态** — 编号叙事，覆盖史诗级异动、AI算力链、软硬分化、中概表现（`_key_dynamics`）
6. **📈 一句话总结** — 全篇收束（`_one_line_summary`）

## 分析维度

`analysis.py` 提供两层分析：
- **数据层** — 大盘定调、板块均涨跌、异动筛选（≥5%）、52周位置
- **叙事层** — 原因简述（启发式：天量成交/板块联动/逼近新高/横盘整理）、表现综述、关键动态编号、一句话总结
