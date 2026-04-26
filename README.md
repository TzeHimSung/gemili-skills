# Gemili Skills

奇奇怪怪的 skills

## Skill 列表

### us-stock-tracker · 美股行情追踪

双数据源美股追踪 —— 新浪财经实时快照 + Yahoo v8 收盘日报。
覆盖 36 只核心科技股 + 4 大指数，含大盘分析、板块轮动、异动提醒（≥5%）、52 周位置。

- **实时快照** `snapshot.py` — 盘中用，秒级刷新
- **收盘日报** `daily_report.py` — 盘后用，分析师风格输出
- **休市检测** — 自动判断夏令时/冬令时，休市发简化消息
- **定时推送** — 每日早 7:00 微信 / 7:10 QQ + Telegram

环境约束：Yahoo v8 必须 curl subprocess（Python requests 被封 403），新浪需 Referer header。

### deep-analysis · 个股深度分析

全流程个股研究引擎 —— 22 维数据采集 → 51 位投资大佬量化评审 → 6 种机构级估值建模（DCF/Comps/LBO/3-Stmt/Merger）→ Bloomberg 风格 HTML 报告 + 社交分享战报。

覆盖 A 股/港股/美股，内含杀猪盘检测、龙虎榜分析、催化剂日历、IC Memo。51 位评委含巴菲特、索罗斯、西蒙斯、段永平、赵老哥、章盟主 等，每位均有独立 persona YAML。

两段式执行：Stage 1 脚本采集 + 量化，Stage 2 agent 介入定性判断后生成报告。强制 self-review 机制，critical 不过不出 HTML。

### anison-live-countdown · 偶像企划 Live 倒计时

每日生成 LoveLive! / BanG Dream! / 偶像大师 未来一年 live 活动倒计时报表。
多日巡回自动拆分，临近活动高亮标记，支持微信/QQ/Telegram 三平台投递。

数据源：官网直爬 + eplus JSON-LD 兜底，偶像大师因官方站全 JS 渲染需走 eplus。

---

## 环境

所有 skill 运行于 WSL 环境。关键约束：

- `proxies={"http": None, "https": None}` 必须设置（不走代理）
- `Referer` header 必带（新浪/日站反爬）
- yfinance / Yahoo Finance Python requests → IP 封禁 429，须 curl subprocess
- 浏览器自动化（Playwright/CDP）不可用 → 全部走 HTTP 直取

## Cron 投递

cronjob `deliver` 管道可正常投递到微信/QQ/Telegram。注意 `send_message` 工具对微信/QQ 不可用（微信 asyncio bug / QQ 频道 ID 失效），日报推送必须用 cronjob deliver。
