---
name: sina-finance-stock-data
description: 通过新浪财经 API 获取美股/指数实时行情数据 — 本环境唯一可靠方案。yfinance/Yahoo/Google/东方财富/浏览器爬虫全部失败。
---

# 新浪财经股票数据 API

本环境中唯一稳定可用的美股数据源。

## 快速使用

```bash
# 全量抓取（36 股 + 6 指数）→ markdown + JSON
python3 scripts/snapshot.py

# 仅科技板块重点股
python3 scripts/snapshot.py --tech-only

# 指定 ticker
python3 scripts/snapshot.py --tickers gb_nvda,gb_tsla,int_dji

# 输出 JSON
python3 scripts/snapshot.py --json

# 程序中调用
python3 -c "
from common import fetch_stocks, fetch_indices, fetch_all
stocks, indices = fetch_all()
for s in stocks[:5]:
    print(f'{s.ticker}: \${s.price} ({s.change_pct:+.2f}%)')
"
```

## 文件结构

```
scripts/
  common.py      # 公共库：HTTP客户端、个股/指数解析、ticker配置、数据结构
  snapshot.py    # 一键入口：抓取 + JSON/markdown 双输出
data/
  snapshot.json  # JSON 快照
  snapshot.md    # Markdown 报表
```

## 核心约束

```python
import requests

headers = {
    "User-Agent": "Mozilla/5.0 ...",
    "Referer": "https://finance.sina.com.cn/",  # ⚠️ 必带
}
r = requests.get(
    f"https://hq.sinajs.cn/list={tickers}",
    headers=headers,
    timeout=15,
    proxies={"http": None, "https": None},  # ⚠️ 必须绕过代理
)
```

## 代码结构

`common.py` 提供：

| 函数 | 用途 |
|------|------|
| `fetch_raw(tickers)` | 批量抓取原始响应 |
| `parse_response(raw)` | 解析为 `StockQuote` / `IndexQuote` 列表 |
| `fetch_stocks([tickers])` | 抓取个股 |
| `fetch_indices([tickers])` | 抓取指数 |
| `fetch_all()` | 全量抓取 |

数据结构：
- `StockQuote`: ticker, name, price, change_pct, change_amt, prev_close, high, low, high_52w, low_52w, volume, time_str
- `IndexQuote`: ticker, name, price, change_pct, change_amt

特殊处理：`gb_sox`（费城半导体）虽然前缀是 `gb_`，但返回 4 字段（指数格式），已特殊处理。

## 已确认失败的所有方案

- ❌ yfinance / Yahoo Finance：IP 全封 429
- ❌ Google Finance / MarketWatch / investing.com：浏览器反爬
- ❌ 东方财富 eastmoney：代理 SSL 不稳定
- ❌ Alpha Vantage / Finnhub：免费额度不足
- ❌ browser_navigate：CDP 超时

## Ticker 速查

### 常用科技股
`gb_nvda gb_tsla gb_aapl gb_msft gb_goog gb_amzn gb_meta gb_nflx gb_avgo gb_qcom gb_arm gb_amd gb_intc gb_smci gb_pltr gb_crm gb_adbe gb_orcl gb_txn gb_asml gb_tsm gb_mrvl gb_now gb_panw gb_crowd gb_snow gb_mdb gb_uber gb_shop`

### 中概股
`gb_pdd gb_baba gb_jd gb_bidu gb_nio gb_li gb_xpev`

### 指数
`int_dji int_nasdaq int_sp500 gb_sox int_hangseng int_nikkei`
