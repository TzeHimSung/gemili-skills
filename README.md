# Gemili Skills

奇奇怪怪的 skills

## Skill 列表

### shared · 共享库

`us-stock-tracker` 与 `cnhk-stock-tracker` 的公共模块，消除 ~720 行重复代码。
提供数据结构（`DailyBar` / `StockQuote` / `IndexQuote`）、HTTP 客户端（参数化 Accept-Language）、
市场状态检测（美股 DST / 假期表 2026-2027）、多日趋势分析（`detect_trend` / `deep_reason`）。
`anison-live-countdown` 也从此导入 `http_get`。

### us-stock-tracker · 美股行情追踪

双数据源美股追踪 —— 新浪财经实时快照 + Yahoo v8 收盘日报。
覆盖 36 只核心科技股 + 4 大指数，含大盘分析、板块轮动、异动提醒、52 周位置、趋势深度分析。

- **实时快照** `snapshot.py` — 盘中用，新浪财经秒级刷新
- **收盘日报** `daily_report.py` — 盘后用，分析师风格输出（大盘概览 → 核心科技股 → 综述 → 异动 → 趋势深度分析 → 关键动态 → 总结）
- **休市检测** — 判断「昨晚美东时间是否为交易日」而非旧逻辑「最新数据距今 ≤4 天」。周一/周日早晨 → 昨晚美东周末 → 输出休市消息不拉数据。覆盖 2026-2027 美股假期。
- **定时推送** — 每日 07:00 Telegram

环境约束：Yahoo v8 必须 curl subprocess（Python requests 被封 403），新浪需 Referer header。

### cnhk-stock-tracker · 中港股行情追踪

与 `us-stock-tracker` 共享核心引擎，覆盖 A 股芯片半导体 + 港股科技 / LLM 概念。
14 A 股 + 16 港股 + Yahoo 5 指数 / 新浪 6 指数，双数据源（新浪实时 + Yahoo v8 盘后），使用 `CNHK_TREND_THRESHOLDS`（15%/5%）替代美股阈值。

- A 股：中芯国际 / 海光信息 / 寒武纪 / 北方华创 / 韦尔股份 / 中微公司 等 14 只
- 港股：腾讯 / 小米 / 阿里 / 美团 / 商汤 / 金山云 等 16 只
- 输出风格与美股版完全对齐
- 含 A 股涨跌停检测、LLM/AI 概念追踪、跨市场联动分析
- 市场时间固定北京时间（无 DST），中港假期表合并查询
- **定时推送** — 每日 16:10 Telegram

### stock-deep-analysis · 个股深度分析

全流程个股研究引擎 —— 22 维数据采集 → 51 位投资大佬量化评审 → 6 种机构级估值建模（DCF/Comps/LBO/3-Stmt/Merger）→ Bloomberg 风格 HTML 报告 + 社交分享战报。

覆盖 A 股/港股/美股，内含杀猪盘检测、龙虎榜分析、催化剂日历、IC Memo。51 位评委含巴菲特、索罗斯、西蒙斯、段永平、赵老哥、章盟主 等，12 位含手写 persona YAML（旗舰档案），39 位 stub 自动生成。

两段式执行：Stage 1 脚本采集 + 量化 → Agent 介入定性判断 + 角色扮演 → Stage 2 生成报告。强制 self-review 机制（13 条规则），critical 不过不出 HTML。

### cron-multi-platform-delivery · Cron 多平台转发

Cron 投递模式已代码化并强制统一：所有启用中的 recurring 内容任务必须 `deliver='telegram:7943831495'`；后台 `Cron投递策略守卫` 每 30 分钟静默审计并自动纠偏，不再使用「1 主 + N 转发器」。

**⚠️ 现状**：微信和 QQ 的 deliver 管道已不可用（微信 = asyncio bug / QQ = 11263 guild auth 系统错误），`send_message` 工具同样不可用。当前所有 cron job 统一走 Telegram。

核心约束：一次性任务/时间戳任务不被拾取，须 `repeat=forever`。`cronjob run` 只是重调度不是立即执行。

### anison-live-countdown · 偶像企划 Live 倒计时

每日生成 LoveLive! / BanG Dream! / 偶像大师 未来一年 live 活动倒计时报表。
多日巡回自动拆分，临近活动高亮标记，Telegram 推送。

数据源：官网直爬 + eplus JSON-LD 兜底，偶像大师因官方站全 JS 渲染需走 eplus。
关键坑点：半角/全角括号不对称（`＜Stage／Date>`）、日期简写三级补全、LoveLive 各系列 URL 差异大。
HTTP 客户端从 `shared/stock_tracker_lib` 导入。

### 5ch-roast · 锐评老日

抓取 5ch.io 实时热帖排行（ikioig 全板勢い）前 100 条，自动过滤电视打卡/偶像例行等无聊帖，
按逆天潜力打分排序，AI 精选 20 条并写入中日双语锐评，`gen_report.py` 自动格式化输出结构化报告。

- **四步管道**：`scraper.py`（100条抓取）→ `filter_score.py`（自动过滤+预打分）→ AI 写入 `_cn_title` + `_ai_commentary` → `gen_report.py`（生成 report.md）
- **板块覆盖**：嫌儲（政治吐槽）/ VIP（混沌）/ なんG / 速＋ / 芸＋ / ゲハ / netidol
- **逆天打分维度**：板块权重 + meme 标签 + 评论数 + 标题特征 + 逆天关键词
- **输出**：`D:\hermes\5ch-reports\YYYY-MM-DD\` 含 raw_data.json / scored.json / report.md
- **板块特征**：每帖标注板块文化（嫌儲=万物转高市、VIP=性癖暴露 等）
- **定时推送** — 每日 22:36 Telegram

数据源为 `https://headline.5ch.io/ikioig/`，5ch 使用 Shift-JIS 编码（实测 `<meta charset="Shift_JIS">`）。
scraper 逐条 HTTP 请求（~90 帖），超时须设 ≥300s。经 2026-04-26 验证，"前39楼灌水乱码"属不实传说，已移除所有无依据的内容过滤。

### yahoo-jp-roast · Yahoo JP 锐评

爬取 Yahoo!ニュース top-picks 热榜，筛除体育类新闻，按评论数排序并保留 Yahoo pickup URL + 原文链接；后续可结合浏览器/评论 AI 摘要生成中文深度锐评。
脚本输出会归档至 `~/.hermes/yahoo-reports/YYYY-MM-DD-roast.md`。

---

## 架构

```
skills/
├── shared/                       ★ 共享库（Python 包）
│   └── scripts/stock_tracker_lib.py
├── us-stock-tracker/             ★ 美股追踪（→ shared）
├── cnhk-stock-tracker/           ★ 中港股追踪（→ shared）
├── anison-live-countdown/        → shared.http_get
├── stock-deep-analysis/          独立（22维采集+51评委+估值建模）
├── 5ch-roast/                    独立（5ch抓取+过滤+AI锐评）
├── yahoo-jp-roast/               独立（Yahoo JP热榜+AI锐评）
└── cron-multi-platform-delivery/ 投递策略代码 + cronjob 投递模式文档
```

## 环境

所有 skill 运行于 WSL 环境。关键约束：

- `proxies={"http": None, "https": None}` 必须设置（不走代理）
- `Referer` header 必带（新浪/日站反爬）
- yfinance / Yahoo Finance Python requests → IP 封禁 429，须 curl subprocess
- 浏览器自动化（Playwright/CDP）不可用 → 全部走 HTTP 直取
- 新浪财经需 `Referer: https://finance.sina.com.cn/`
- Bang Dream 官网浏览器被 Bot 检测返回 404，须 curl + User-Agent

## Cron 投递

| 时间 | 任务 | Skill |
|------|------|-------|
| 07:00 | 📊 美股收盘日报 | us-stock-tracker |
| 08:35 | 🎵 偶像企划Live倒计时 | anison-live-countdown |
| 12:10 | 📈 中港股午市快报 | cnhk-stock-tracker |
| 16:10 | 🇭🇰 中港股收盘日报 | cnhk-stock-tracker |
| 22:00 | 🗾 Yahoo JP 锐评 | yahoo-jp-roast |

全部通过 cronjob 投递到 Telegram：内容任务强制 `deliver='telegram:7943831495'`，后台守卫每 30 分钟自动纠偏。微信/QQ deliver 暂不可用（平台层 bug，详见 `cron-multi-platform-delivery` skill）。投递策略可用 `cron-multi-platform-delivery/scripts/delivery_policy.py` 审计。
