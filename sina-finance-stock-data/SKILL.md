---
name: sina-finance-stock-data
description: 通过新浪财经 API 获取美股/指数实时行情数据 — 本环境唯一可靠方案。yfinance/Yahoo/Google/东方财富/浏览器爬虫全部失败。
---

# 新浪财经股票数据 API

本环境中唯一稳定可用的美股数据源。其他途径都会失败：
- ❌ yfinance：Yahoo 封数据中心 IP，全部 429/超时
- ❌ Google Finance / MarketWatch / investing.com：浏览器爬虫全部被反爬
- ❌ 东方财富 eastmoney：代理 SSL 错误，不稳定
- ❌ Alpha Vantage / Finnhub / MarketStack：免费额度不足需 API key

## 核心 API

```
GET https://hq.sinajs.cn/list=gb_nvda,gb_tsla,int_dji,int_nasdaq,gb_sox
```

### 必须参数
- **Headers**: `Referer: https://finance.sina.com.cn/`（不传会被拒）
- **Proxy bypass**: `proxies={'http': None, 'https': None}`（绕过本地代理）

### 美股个股代码
格式：`gb_<小写ticker>`，如 `gb_nvda`, `gb_tsla`, `gb_aapl`

### 美股指数代码
| 指数 | 代码 |
|------|------|
| 道琼斯 | `int_dji` |
| 纳斯达克 | `int_nasdaq` |
| S&P 500 | `int_sp500` |
| 费城半导体 SOX | `gb_sox` |

## 返回格式解析

### 个股（gb_xxx）
```
var hq_str_gb_NVDA="名称,当前价,涨跌幅%,日期时间,涨跌额,昨收,最高,最低,52周高,52周低,成交量,..."
```
字段索引：0=名称, 1=当前价, 2=涨跌幅(%), 3=日期时间, 4=涨跌额, 5=昨收, 6=最高, 7=最低, 8=52周高, 9=52周低, 10=成交量

### 指数（int_xxx）
```
var hq_str_int_dji="名称,当前价,涨跌额,涨跌幅%"
```
字段索引：0=名称, 1=当前价, 2=涨跌额, 3=涨跌幅(%)

## 示例代码

```python
import requests

headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'}
stocks = "gb_nvda,gb_tsla,gb_aapl,int_dji,int_nasdaq,int_sp500,gb_sox"
url = f"https://hq.sinajs.cn/list={stocks}"

r = requests.get(url, headers=headers, timeout=15, proxies={'http': None, 'https': None})

for line in r.text.strip().split('\n'):
    if '=""' in line or not line.strip():
        continue
    parts = line.split('="')
    ticker = parts[0].replace('var hq_str_', '')
    fields = parts[1].rstrip('";').split(',')
    
    if ticker.startswith('int_'):
        name, price, change, change_pct = fields[0], fields[1], fields[2], fields[3]
        print(f"{name}: {price} ({change_pct}%)")
    else:
        name, price, pct, dt, change, prev, high, low, h52, l52, vol = fields[:11]
        print(f"{name} ({ticker}): ${price} {pct}% | 52w: {l52}-{h52}")
```

## 常用科技股代码

`gb_avgo,gb_qcom,gb_arm,gb_smci,gb_pltr,gb_crm,gb_adbe,gb_orcl,gb_txn,gb_amzn,gb_meta,gb_nflx,gb_asml,gb_tsm,gb_mrvl,gb_now,gb_panw,gb_crowd,gb_snow,gb_mdb,gb_uber,gb_shop`
