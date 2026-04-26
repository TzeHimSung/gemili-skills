# Gemili Skills

Hermes Agent 的自定义技能集合。

## 技能列表

### sina-finance-stock-data
美股数据源。本服务器环境唯一可靠方案——通过新浪财经 API (hq.sinajs.cn) 获取美股/指数实时行情数据。

环境限制：
- yfinance/Yahoo Finance：IP 全封 429
- Google Finance / MarketWatch：浏览器反爬
- 东方财富：代理 SSL 不稳定

### deep-analysis
个股深度分析。包含数据采集、多维度评分、投资人画像分析、报告生成的完整 pipeline。支持 50+ 投资人角色（巴菲特/索罗斯/西蒙斯/林奇等）视角评估。

### anison-live-countdown
每日生成 LoveLive / BanG Dream / 偶像大师 未来一年 live 活动倒计时报表。

数据来源：
- bang-dream.com（官方站，Python requests 直取，绕过 Bot 检测）
- lovelive-anime.jp（蓮ノ空 live-event 页面）
- idolmaster-official.jp（各品牌 live_event 详情页）
- eplus.jp（JSON-LD 结构化数据补漏）

支持三平台投递：微信 / QQ / Telegram
