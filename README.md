# Gemili Skills

奇奇怪怪但可复用的 Hermes Agent skills 仓库。当前常规维护 **12 个 skill**（另有大型独立 `stock-deep-analysis`），覆盖股票行情、新闻锐评、旅行查询、系统维护、备份与 cron 投递策略。

> 默认运行环境：WSL / Linux。运行时 skills 通常位于 `~/.hermes/skills/`；本仓库是可版本管理的源码副本 `~/gemili-skills`。

## Skill 列表

### shared · 共享库

`us-stock-tracker` 与 `cnhk-stock-tracker` 的公共 Python 模块，消除重复行情/市场状态/趋势分析逻辑。
提供数据结构（`DailyBar` / `StockQuote` / `IndexQuote`）、HTTP 客户端（参数化 `Accept-Language`）、市场状态检测（美股 DST / 2026-2027 假期表）、多日趋势分析（`detect_trend` / `deep_reason_base`）。
`anison-live-countdown` 也从此导入 `http_get`。

### us-stock-tracker · 美股行情追踪

双数据源美股追踪 —— 新浪财经实时快照 + Yahoo v8 收盘日报。
覆盖核心科技股与主要指数，含大盘分析、板块轮动、异动提醒、52 周位置、趋势深度分析。

- **实时快照**：`scripts/snapshot.py` — 盘中用，新浪财经秒级刷新
- **收盘日报**：`scripts/daily_report.py` — 盘后分析师风格输出
- **休市检测**：判断「昨晚美东时间是否为交易日」，覆盖 2026-2027 美股假期；周一/周日早晨不会误拉周末数据
- **定时推送**：每日 07:00，Telegram+微信双投

环境约束：Yahoo v8 必须走 curl subprocess（Python requests 易 403/429），新浪需 `Referer: https://finance.sina.com.cn/`。

### cnhk-stock-tracker · 中港股行情追踪

与 `us-stock-tracker` 共享核心引擎，覆盖 A 股芯片半导体 + 港股科技 / LLM 概念。
双数据源（新浪实时 + Yahoo v8 盘后），使用 `CNHK_TREND_THRESHOLDS`（15%/5%）替代美股阈值。

- A 股：中芯国际 / 海光信息 / 寒武纪 / 北方华创 / 韦尔股份 / 中微公司 等
- 港股：腾讯 / 小米 / 阿里 / 美团 / 商汤 / 金山云 等
- 含 A 股涨跌停检测、LLM/AI 概念追踪、跨市场联动分析
- 市场时间固定北京时间（无 DST）；A 股 / 港股假期分别判断，只有两地同日休市才整体休市
- **定时推送**：每日 12:00 午市快报、16:10 收盘日报，Telegram+微信双投

### stock-deep-analysis · 个股深度分析

全流程个股研究引擎 —— 22 维数据采集 → 51 位投资大佬量化评审 → 6 种机构级估值建模（DCF/Comps/LBO/3-Stmt/Merger）→ Bloomberg 风格 HTML 报告 + 社交分享战报。

覆盖 A 股/港股/美股，内含杀猪盘检测、龙虎榜分析、催化剂日历、IC Memo。51 位评委含巴菲特、索罗斯、西蒙斯、段永平、赵老哥、章盟主等；其中 12 位旗舰 persona 手写维护，39 位 stub 自动生成。

两段式执行：Stage 1 脚本采集 + 量化 → Agent 介入定性判断 + 角色扮演 → Stage 2 生成报告。强制 self-review 机制（当前代码注册 16 条检查），critical 不过不出 HTML。

### cron-multi-platform-delivery · Cron 多平台投递

Cron 投递模式已代码化并强制统一：所有启用中的 recurring **内容任务**必须使用 Telegram+微信双投递（`deliver='telegram:[REDACTED],weixin:[REDACTED]'`）；后台 `Cron投递策略守卫` 每 30 分钟静默审计并自动纠偏，不再使用「1 主 + N 转发器」。

核心约束：一次性任务/时间戳任务不作为 recurring 守卫目标；创建 recurring schedule 时省略 `repeat` 即默认 forever（不要传 `repeat='forever'`，该参数是整数）。系统维护任务使用 `deliver=local`。

### update-fedora-packages · Fedora 软件包更新

在 Fedora / WSL 环境中以非交互方式刷新仓库并更新系统软件包。后台 cron 使用 `sudo -n dnf5 upgrade --refresh -y`，避免等待密码导致任务卡死；只做当前 Fedora release 内的软件包更新，不执行发行版大版本升级。

- **定时执行**：每日 10:00，本地 `deliver=local` 静默保存输出，不向 Telegram / 微信发送消息

### anison-live-countdown · 偶像企划 Live 倒计时

每日生成 LoveLive! / BanG Dream! 未来一年 live 活动倒计时报表；偶像大师已按用户偏好停用，即使历史目录残留 `idolmaster.json` 也不会展示。
多日巡回自动拆分，临近活动高亮标记，Markdown 表格每页最多 20 条；脚本生成 Telegram/微信兼容正文，实际推送由 Hermes cronjob 双投递。

数据源：BanG Dream! 官网直爬（curl/User-Agent 规避 Bot 检测）+ LoveLive! 官网直爬；eplus JSON-LD 目前主要作为已验证的数据源经验，尚未接入默认 LoveLive/BanG Dream 日报管道。
关键坑点：半角/全角括号不对称（`＜Stage／Date>`）、日期简写三级补全、LoveLive 各系列 URL 差异大、报告必须过滤已结束 live。

### 5ch-roast · 5ch 热帖锐评

抓取 5ch.io 实时热帖排行（ikioig 全板勢い）前 100 条，自动过滤电视打卡/偶像例行等无聊帖，按逆天潜力打分排序，AI 精选 20 条并写入中日双语锐评，`gen_report.py` 自动格式化输出结构化报告。

- **四步管道**：`scraper.py`（100条抓取）→ `filter_score.py`（自动过滤+预打分）→ AI 写入 `_cn_title` + `_ai_commentary` → `gen_report.py`（生成 report.md）
- **板块覆盖**：嫌儲 / VIP / なんG / 速＋ / 芸＋ / ゲハ / netidol
- **逆天打分维度**：板块权重 + meme 标签 + 评论数 + 标题特征 + 逆天关键词
- **输出**：默认 `D:\hermes\5ch-reports\YYYY-MM-DD\`（WSL 下 `/mnt/d/hermes/5ch-reports/...`），含 raw_data.json / scored.json / report.md
- **定时状态**：当前未配置 cron 定时任务，按需手动执行

数据源为 `https://headline.5ch.io/ikioig/`，5ch 使用 Shift-JIS 编码。逐条 HTTP 请求耗时较长，超时需设 ≥300s。

### yahoo-jp-news-scraper · Yahoo Japan News 热榜抓取

底层抓取/研究型 skill：爬取 Yahoo!ニュース `top-picks` 热榜、pickup 页、article 页和 comments 页，提取正文摘要、评论数与 **ヤフコメAI要約**。

- `top-picks` 静态 HTML 当前可解析 `commentCount`；若页面形状变化应失败或回退，不能静默产错排名
- pickup 页优先用 curl + User-Agent，评论 AI 要約可用浏览器 fallback
- 评论页可能 404、评论关闭或网络瞬断，需重试并标明不可用原因

### yahoo-jp-roast · Yahoo JP 中文锐评日报

面向最终报告的 Yahoo JP 热榜锐评 skill。筛除体育类新闻，按评论数与话题性排序，保留 Yahoo pickup URL + 原文链接，结合正文摘要和评论 AI 总结生成中文深度锐评。

- **报告归档**：no-agent 安全日报使用 `~/.hermes/yahoo-reports/YYYY-MM-DD-roast-safe.md`；研究/调试脚本仍可生成 `YYYY-MM-DD-roast.md`
- **定时推送**：每日 22:00，Telegram+微信双投
- **用户偏好**：报告正文至少 20 条；开头不放 Top10/Top20 元数据汇总，元数据随每条新闻展示

### kaikatsu-club-vacancy · 快活CLUB 空席查询

输入日本地名/车站/机场名，定位后查询最近 3 家快活CLUB，并输出官网实时空席接口返回的每一种席种/房型状态（如 `満席`、`残4席`、`残10席以上`）。

数据源：快活CLUB `data/shop.js` 店铺列表 + 各店详情页 Google Maps 坐标 + 官网 `empty_seat` 空席 API；地名定位用 OpenStreetMap Nominatim，国土地理院地址搜索兜底。首次运行会缓存约 500 家店铺坐标到 `~/.cache/hermes/kaikatsu-club-vacancy/`，后续查询直接复用。

### flight-search · 航班直飞查询

按出发地、目的地、出发日期、单程/往返标记查询直飞航班，输出实际执飞航班、销售/共享航班号、机场/航站楼、当地起降时间、机型、可验证机龄、舱位与价格来源。

- **固定脚本**：`scripts/flight_search.py`
- **默认范围**：只查直飞 / non-stop；中转、多城市行程暂不展开
- **时刻来源**：FlightStats / Cirium 公共页面与 `api-next` JSON
- **价格来源**：可选 Amadeus Flight Offers（`AMADEUS_CLIENT_ID` / `AMADEUS_CLIENT_SECRET`）与 Kiwi/Tequila（`TEQUILA_API_KEY` 或 `KIWI_TEQUILA_API_KEY`）；没有凭据时只报告航班时刻，不编造价格
- **输入格式**：IATA 三字码优先；日期支持 `YYYY-MM-DD`、`YYYYMMDD`、`MMDD`；往返时返回日期按出发日期之后的最近日期推断
- **快捷命令**：可由 Hermes `/flight [出发地] [目的地] [出发日期] [返回日期(可选)]` 调用

### hermes-snapshot · Hermes 全量备份

当用户说“备份自己 / 全量备份 / Hermes snapshot”时，运行固定脚本执行 `hermes backup`，把备份 zip 写入本仓库 `hermes_snapshot/`，保留最新 3 份并提交推送。该 skill 明确只 stage `hermes_snapshot/`，避免备份流程顺手提交无关 skill 改动。

- **固定脚本**：`hermes-snapshot/scripts/hermes_snapshot_backup.sh`
- **备份目录**：`hermes_snapshot/hermes-backup-*.zip`
- **验证**：zip 非空、`unzip -t` 通过、retention 删除包含在同一 commit

## 架构

```text
~/gemili-skills/
├── shared/                       ★ 共享库（Python 包）
│   ├── scripts/stock_tracker_lib.py
│   └── tests/test_market_status.py
├── us-stock-tracker/             ★ 美股追踪（→ shared）
├── cnhk-stock-tracker/           ★ 中港股追踪（→ shared）
├── anison-live-countdown/        → shared.http_get
├── stock-deep-analysis/          独立（22维采集+51评委+估值建模）
├── 5ch-roast/                    独立（5ch抓取+过滤+AI锐评）
├── yahoo-jp-news-scraper/        独立（Yahoo JP热榜/正文/评论AI要約抓取）
├── yahoo-jp-roast/               独立（Yahoo JP热榜+中文AI锐评）
├── kaikatsu-club-vacancy/        独立（快活CLUB最近三店+空席API）
├── flight-search/                独立（直飞航班时刻+可选价格交叉验证）
├── hermes-snapshot/              Hermes 全量备份 skill（脚本化 hermes backup）
├── hermes_snapshot/              备份 zip 归档目录（保留最新 3 份）
├── update-fedora-packages/       Fedora / WSL 软件包后台更新
├── cron-multi-platform-delivery/ 投递策略代码 + cronjob 投递模式文档
├── scripts/skills_audit.py       仓库离线安全/文档漂移审计
└── tests/                        跨 skill 回归测试
```

## 环境与数据源约束

所有 skill 运行于 WSL 环境。关键约束：

- `proxies={"http": None, "https": None}` 必须设置（不走代理）
- `Referer` header 必带（新浪/日站反爬）
- yfinance / Yahoo Finance Python requests → 易 IP 封禁 429，须 curl subprocess
- 浏览器自动化（Playwright/CDP）并非所有站都可靠，优先 HTTP 直取 + 必要时浏览器 fallback
- 新浪财经需 `Referer: https://finance.sina.com.cn/`
- Bang Dream 官网浏览器被 Bot 检测返回 404，须 curl + User-Agent
- OTA/航旅站点若出现 captcha/challenge，不绕过；只能报告已实际看到或 API 返回的价格

## Cron 投递

当前 cronjob 配置（北京时间）：

| 时间 | 任务 | Skill / 来源 | 投递 |
|------|------|--------------|------|
| 07:00 | 📊 美股收盘日报 | `us-stock-tracker` | Telegram+微信 |
| 09:00 | 🎵 偶像企划 Live 倒计时 | `anison-live-countdown` | Telegram+微信 |
| 10:00 | 🛠️ Fedora 软件包每日更新 | `update-fedora-packages` | local 静默 |
| 12:00 | 📈 中港股午市快报 | `cnhk-stock-tracker` | Telegram+微信 |
| 14:00 | 🔄 Hermes 自动更新 + gateway/cron 健康检查 | systemd user timer | local 日志 |
| 16:10 | 🇭🇰 中港股收盘日报 | `cnhk-stock-tracker` | Telegram+微信 |
| 22:00 | 🗾 Yahoo JP 锐评日报 | `yahoo-jp-roast` | Telegram+微信 |
| */30 | 🧭 Cron 投递策略守卫 | `cron-multi-platform-delivery` | local 静默 |

内容任务通过 cronjob 单任务直投 Telegram+微信：强制 `deliver='telegram:[REDACTED],weixin:[REDACTED]'`，后台守卫每 30 分钟自动纠偏。系统维护任务（如 Fedora 软件包每日更新、投递策略守卫）使用 `deliver=local` 静默执行。QQ/qqbot 仍不启用；投递策略可用 `cron-multi-platform-delivery/scripts/delivery_policy.py` 审计。

## 本次全仓扫描结论（代码化候选）

本仓库维护时优先把重复业务规则从 prompt/文档迁入脚本、审计器或单元测试，避免 cron 与报告格式再次漂移。当前已代码化的守门项包括：

- `scripts/skills_audit.py`：AST 语法检查、Markdown 投递目标脱敏检查、Yahoo JP no-agent 安全日报契约检查、README/GitHub workflow skill inventory 审计；
- `cron-multi-platform-delivery/scripts/delivery_policy.py`：内容任务 Telegram+微信双投递、维护任务 `local` 静默、一次性/时间戳任务不被误纠偏的投递策略；
- `yahoo-jp-roast/scripts/yahoo_rules.py`：体育过滤词与 allowlist 单源化，手动脚本和 no-agent 安全日报共用同一规则；
- `yahoo-jp-roast/scripts/safe_daily_report.py`：JST 时间、pickup 去重、自动扩页直到满足 20 条非体育新闻，不足则失败而不是投递低质量日报；
- `5ch-roast/scripts/gen_report.py`：默认禁止“AI 锐评待补”骨架和不足 20 条的半成品报告出货，除非显式 `--allow-skeleton` / `--allow-partial`；
- `anison-live-countdown/scripts/common.py`：多日巡回日期拆分支持 `・`、斜杠与 `〜/～` 范围写法；
- `tests/test_news_roast.py`、`tests/test_stock_trackers.py`、`cron-multi-platform-delivery/tests/test_delivery_policy.py`：Yahoo/5ch/中港股 ticker/cron recurring 判定等回归测试。

后续最值得继续代码化的业务逻辑：

1. `flight-search`：城市/机场别名→IATA、往返总价与单航段价格分离、价格 deep link 来源输出；
2. `anison-live-countdown`：统一 JST today、LoveLive/BanG Dream HTML fixture 与 URL 表一致性测试；
3. `kaikatsu-club-vacancy`：Nominatim 多候选评分、店铺坐标缓存完整性阈值；
4. `stock-deep-analysis`：22/23 维 commentary/schema 完整性、20-22 维 pipeline parity、stub 高分禁止规则（需单独明确授权后改动）；
5. `update-fedora-packages`：把 prompt 中的 dnf5/dnf/sudo -n 流程进一步落成固定脚本与 dry-run 测试。

## 本地校验

推荐在提交前运行：

```bash
cd ~/gemili-skills
PYTHONDONTWRITEBYTECODE=1 python3 scripts/skills_audit.py .
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests shared/tests anison-live-countdown/tests cron-multi-platform-delivery/tests kaikatsu-club-vacancy/tests -q
git diff --check
```

`stock-deep-analysis/` 较大且有独立历史约束；除非明确维护它，否则常规仓库维护不应改动该目录。
