---
name: shared
description: 共享 Python 库 — 为 us/cnhk-stock-tracker 提供公共数据结构和分析函数。非独立 skill，被其他 skill 作为 Python 包导入。
---

# Shared · 股票追踪共享库

被 `us-stock-tracker`、`cnhk-stock-tracker`、`anison-live-countdown` 导入的公共 Python 库。
提供数据结构（`DailyBar` / `StockQuote` / `IndexQuote`）、HTTP 客户端、市场状态检测、
多日趋势分析、假期表（2026-2027）。

## 提供的模块

| 函数 | 说明 |
|------|------|
| `http_get(url, accept_lang=...)` | 参数化 Accept-Language 的 HTTP GET |
| `detect_trend(stock, thresholds)` | 多日趋势检测（支持美股/中港股阈值） |
| `deep_reason_base(stock, all_stocks, sectors, ...)` | 深度原因分析框架 |
| `trend_analysis_section(stocks, sectors, ...)` | 走势深度分析段落生成 |
| `check_market_status(stocks, indices, hours_fn)` | 市场状态检测 |
| `closed_reason(latest_date, days_behind, market)` | 休市原因推断 |
| `fifty_two_week_text(stock)` | 52周位置文案 |
| `fifty_two_week_check(stocks)` | 52周高/低点检测 |

## 重构陷阱（2026-04-26 踩坑记录）

从 us-stock-tracker 和 cnhk-stock-tracker 抽取公共代码时遇到的 3 个 bug：

### 1. 模块级变量覆写导致递归调用
```python
# ❌ 错误：_trend_analysis_section 先导入共享库函数，后被 wrapper 覆写，
#    wrapper 内部又调用同名全局变量 → 递归 + 参数错位
from common import _trend_analysis_section
def wrapper(stocks, top_n=3):
    return _trend_analysis_section(stocks, SECTORS, top_n=top_n)
_trend_analysis_section = wrapper

# ✅ 正确：用不同名字导入，wrapper 内部调用原名
from common import _trend_analysis_section as _shared_tsa
def wrapper(stocks, top_n=3):
    return _shared_tsa(stocks, SECTORS, top_n=top_n)
_trend_analysis_section = wrapper
```

### 2. 同名函数参数签名冲突
```python
# ❌ 错误：display_name(stock, name_map) 是 2 参数共享库函数，
#   但 as _display_name 绑定后覆盖了 common.py 里的本地 1 参数 wrapper
from common import display_name as _display_name

# ✅ 正确：不在 import 里起别名，直接在本地定义 wrapper
from common import YAHOO_STOCKS_CN, StockQuote
def _display_name(stock):
    return YAHOO_STOCKS_CN.get(stock.ticker.upper(), stock.name)
```

### 3. 回调函数签名与实际调用不匹配
```python
# ❌ 错误：extra_checks_fn 签名是 (stock, direction, trend)，
#   但调用处只传了 extra_checks_fn(s)
lines.append(f"...{deep_reason_base(s, ..., extra_checks_fn(s))}")

# ✅ 正确：传入完整参数
trend = detect_trend(s, thresholds)
lines.append(f"...{deep_reason_base(s, ..., extra_checks_fn(s, trend['direction'], trend))}")
```

## 数据验证方法

"前39楼灌水乱码"经实际数据验证（89帖 2139评）不属实。验证方法：
```python
# 量化检查：统计实际匹配模式的评论数
garbled = sum(1 for t in threads for c in t['comments']
              if text.count('チョン') >= 2 or text.count('パヨ') >= 2)
# 结果：0 / 2139
```
教训：不依赖未经验证的文档陈述，实测数据后再下结论。
