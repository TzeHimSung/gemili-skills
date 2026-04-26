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
  common.py         # HTTP客户端、双源ticker配置、StockQuote/IndexQuote、板块分组
  analysis.py       # 分析引擎（大盘定调、板块均涨跌、异动筛选、52周位置）
  snapshot.py       # 新浪财经实时快照（盘中）
  daily_report.py   # Yahoo v8 收盘日报（盘后）
```

## 双数据源

| 数据源 | 端点 | 用途 | 特点 |
|--------|------|------|------|
| 新浪财经 | `hq.sinajs.cn/list=` | 实时快照 | 需要 `Referer` header + 绕过代理 |
| Yahoo v8 | `query1.finance.yahoo.com/v8/finance/chart/` | 收盘日报 | 5日 OHLC + 52周高低 + 成交量 |

## 环境约束

```python
# 必须设置
proxies = {"http": None, "https": None}
headers = {"User-Agent": "Mozilla/5.0 ..."}

# 新浪额外需要
headers["Referer"] = "https://finance.sina.com.cn/"
```

## Cron 使用

主任务直接运行脚本：
```
python3 ~/.hermes/skills/us-stock-tracker/scripts/daily_report.py
```

## 分析维度

`analysis.py` 自动生成：
- **大盘定调** — 偏多/偏空/分化
- **板块分析** — 半导体/软件云/消费科技/中概 分别计算均涨跌
- **异动提醒** — 涨跌幅 ≥ 5%
- **52周位置** — 接近历史高/低点梳理
