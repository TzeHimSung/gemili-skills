# Gemili Skills

奇奇怪怪但可复用的 Hermes Agent skills 仓库。当前常规维护 **13 个 skill**（另有大型独立 `stock-deep-analysis`，仓库实际包含 14 个顶层 `SKILL.md`），覆盖股票行情、新闻锐评、旅行查询、系统维护、备份、开发准则与 cron 投递策略。

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
- 市场时间固定北京时间（无 DST）；A 股 / 港股假期分别判断，只有两地同日休市才整体休市；混合 A+H 请求会保留原始市场范围，单边休市时过滤休市市场报价，避免把 A 股休市误写成整体休市或静默降级
- **定时推送**：每日 12:00 午市快报、16:10 收盘日报，Telegram+微信双投

### stock-deep-analysis · 个股深度分析

全流程个股研究引擎 —— 24 个报告维度采集/计算（0-22，其中 `6_fund_holders` 与 `6_research` 分列）→ 51 位投资大佬量化评审 → 多种机构级估值建模（DCF/Comps/LBO/3-Stmt/Merger 等）→ Bloomberg 风格 HTML 报告 + 社交分享战报。

覆盖 A 股/港股/美股，内含杀猪盘检测、龙虎榜分析、催化剂日历、IC Memo。51 位评委含巴菲特、索罗斯、西蒙斯、段永平、赵老哥、章盟主等；其中 12 位旗舰 persona 手写维护，39 位 stub 自动生成。

两段式执行：Stage 1 脚本采集 + 量化 → Agent 介入定性判断 + 角色扮演 → Stage 2 生成报告。强制 self-review 机制（当前代码注册 16 条检查），critical 不过不出 HTML。`agent_analysis_validator.py` 目前保持“结构/类型/短内容告警”型宽松 schema：它校验 `REQUIRED_DIM_KEYS` 常量覆盖 v3 registry 的 24 个报告维度（含 `6_fund_holders`），但不把 `dim_commentary` 全维缺失升级为 error；实际完成标准仍以 `stock-deep-analysis/SKILL.md` 的 agent 审查流程为准。测试和运行缓存统一走 `UZI_CACHE_DIR` / `lib.cache.CACHE_ROOT`；`total_funds_holding` / `funds_holding_count` 只表示基金数量（只），只有 `fund_holding_pct` / `total_holding_pct` 可作为百分比展示或加分。

### cron-multi-platform-delivery · Cron 多平台投递

Cron 投递目标策略已代码化为审计器：所有启用中的 recurring **内容任务**应使用 Telegram+微信双投递（`deliver='telegram:[REDACTED],weixin:[REDACTED]'`）；后台 `Cron投递策略守卫` 每 30 分钟静默审计，目标是不再使用「1 主 + N 转发器」。一次性/时间戳任务识别、缺失 secret 时 fail-closed、live inventory 纠偏都已纳入第一批修复与验证；真实 Telegram / 微信 target 仍只能来自环境变量、本机私密文件或运行时配置，不能写入 Git。

目标约束：一次性任务/时间戳任务不应作为 recurring 守卫目标；创建 recurring schedule 时省略 `repeat` 即默认 forever（不要传 `repeat='forever'`，该参数是整数）。系统维护任务使用 `deliver=local`。live 守卫缺少真实 target 时应 fail closed，而不是回退到可误用的 dummy target。

### update-fedora-packages · Fedora 软件包更新

在 Fedora / WSL 环境中以非交互方式刷新仓库并更新系统软件包。后台 cron 直接调用 `update-fedora-packages/scripts/update_fedora_packages.sh`，脚本内固定 `sudo -n`、`dnf5` 优先/`dnf` fallback、dry-run 验证和当前 release 内升级流程，避免等待密码导致任务卡死；不执行发行版大版本升级。

- **定时执行**：每日 10:00，本地 `deliver=local` 静默保存输出，不向 Telegram / 微信发送消息
- **回归测试**：`update-fedora-packages/tests/test_update_fedora_packages.py` 覆盖脚本可执行性、非交互 sudo、dry-run 检查命令与文档引用

### anison-live-countdown · 偶像企划 Live 倒计时

每日生成 LoveLive! / BanG Dream! 未来一年 live 活动倒计时报表；偶像大师已按用户偏好停用，即使历史目录残留 `idolmaster.json` 也不会展示。
多日巡回自动拆分，临近活动高亮标记，Markdown 表格每页最多 20 条；脚本生成 Telegram/微信兼容正文，实际推送由 Hermes cronjob 双投递。

数据源：BanG Dream! 官网直爬（Python requests + User-Agent/Referer 规避浏览器 Bot 检测）+ LoveLive! 官网直爬；eplus JSON-LD 目前主要作为已验证的数据源经验，尚未接入默认 LoveLive/BanG Dream 日报管道。
关键坑点：半角/全角括号不对称（`＜Stage／Date>`）、日期简写三级补全、LoveLive 各系列 URL 差异大、报告必须过滤已结束 live；日期统一以 JST today 判定，BanG Dream / LoveLive 默认官方 URL 表由 `test_official_sources.py` 锁定，避免误把 Idolmaster 残留源重新纳入日报。

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

数据源：快活CLUB `data/shop.js` 店铺列表 + 各店详情页 Google Maps 坐标 + 官网 `empty_seat` 空席 API；地名定位用 OpenStreetMap Nominatim 多候选评分（精确站名/机场名优先，泛行政区降权），国土地理院地址搜索兜底。首次运行会缓存约 500 家店铺坐标到 `~/.cache/hermes/kaikatsu-club-vacancy/`，低于坐标完整率阈值会失败而不是缓存半成品，后续查询直接复用。

### flight-search · 航班直飞查询

按出发地、目的地、出发日期、单程/往返标记查询直飞航班，输出实际执飞航班、销售/共享航班号、机场/航站楼、当地起降时间、机型、可验证机龄、舱位与价格来源。

- **固定脚本**：`scripts/flight_search.py`
- **默认范围**：只查直飞 / non-stop；中转、多城市行程暂不展开
- **时刻来源**：FlightStats / Cirium 公共页面与 `api-next` JSON
- **价格来源**：可选 Amadeus Flight Offers（`AMADEUS_CLIENT_ID` / `AMADEUS_CLIENT_SECRET`）与 Kiwi/Tequila（`TEQUILA_API_KEY` 或 `KIWI_TEQUILA_API_KEY`）；没有凭据时只报告航班时刻，不编造价格；往返报价会区分去程/返程、保留总价说明，并把 booking deep link 作为来源输出
- **输入格式**：IATA 三字码或已知中文/日文城市机场别名；日期支持 `YYYY-MM-DD`、`YYYYMMDD`、`MMDD`；往返时返回日期按出发日期之后的最近日期推断
- **快捷命令**：可由 Hermes `/flight [出发地] [目的地] [出发日期] [返回日期(可选)]` 调用

### hermes-snapshot · Hermes 全量备份

当用户说“备份自己 / 全量备份 / Hermes snapshot”时，运行固定脚本执行 `hermes backup`，在本地生成明文 zip 与加密 zip.gpg；Git 只维护 `.gitignore`、`hermes_snapshot/manifest.json` 和脚本文档，备份二进制保持忽略并通过 GitHub Release / 本地留存交付，避免把完整 Hermes 备份提交进仓库历史。

- **固定脚本**：`hermes-snapshot/scripts/hermes_snapshot_backup.sh`；cron 使用 `hermes_snapshot_cron.sh` no-agent 模式
- **本地备份**：`hermes_snapshot/hermes-backup-*.zip` 与 `*.zip.gpg`（Git ignore；manifest 记录摘要与 retention）
- **定时执行**：每日 23:00，本地 `deliver=local`；GitHub Release 上传需要已认证 `gh` 或 `HERMES_SNAPSHOT_GITHUB_TOKEN` / `GITHUB_TOKEN` / `GH_TOKEN`
- **验证**：zip 非空、`unzip -t` 通过、GPG 加密产物存在、manifest/retention 更新包含在同一 commit

### repo-development-guidelines · 仓库开发准则

高优先级开发 guardrail：任何个人仓库或工作仓库修改前都必须加载并遵守 Superpowers 基本流程，避免 agent 直接跳进改代码。

- **适用范围**：`~/gemili-skills` 等个人仓库、`~/code/netease` 等工作仓库，以及任何会进入 git diff / commit / PR 的变更
- **基本流程**：需求/意图澄清 → 设计/spec → `git status` 与隔离分支/ worktree → bite-sized plan → TDD 或文档 validator → diff review / tests → commit/push/merge 前明确收尾选择
- **保护规则**：发现 unrelated dirty changes 时先停下；默认不碰 `stock-deep-analysis/`；默认不强推、不绕过分支保护，main 被保护时走 feature branch + PR

## 架构

```text
~/gemili-skills/
├── shared/                       ★ 共享库（Python 包）
│   ├── scripts/stock_tracker_lib.py
│   └── tests/test_market_status.py
├── us-stock-tracker/             ★ 美股追踪（→ shared）
├── cnhk-stock-tracker/           ★ 中港股追踪（→ shared）
├── anison-live-countdown/        → shared.http_get
├── stock-deep-analysis/          独立（24维报告契约+51评委+估值建模）
├── 5ch-roast/                    独立（5ch抓取+过滤+AI锐评）
├── yahoo-jp-news-scraper/        独立（Yahoo JP热榜/正文/评论AI要約抓取）
├── yahoo-jp-roast/               独立（Yahoo JP热榜+中文AI锐评）
├── kaikatsu-club-vacancy/        独立（快活CLUB最近三店+空席API）
├── flight-search/                独立（直飞航班时刻+可选价格交叉验证）
├── hermes-snapshot/              Hermes 全量备份 skill（脚本化 hermes backup）
├── hermes_snapshot/              备份 zip 归档目录（保留最新 3 份）
├── repo-development-guidelines/  高优先级仓库开发准则（Superpowers 基本流程）
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
- Bang Dream 官网浏览器被 Bot 检测返回 404，须用 HTTP 直取并带 User-Agent/Referer
- OTA/航旅站点若出现 captcha/challenge，不绕过；只能报告已实际看到或 API 返回的价格

## Cron 投递

当前与本仓库 / 个人系统维护直接相关的 cronjob 配置（北京时间）：

| 时间 | 任务 | Skill / 来源 | 投递 |
|------|------|--------------|------|
| 07:00 | 📊 美股收盘日报 | `us-stock-tracker` | Telegram+微信 |
| 09:00 | 🎵 偶像企划 Live 倒计时 | `anison-live-countdown` | Telegram+微信 |
| 10:00 | 🛠️ Fedora 软件包每日更新 | `update-fedora-packages` | local 静默 |
| 12:00 | 📈 中港股午市快报 | `cnhk-stock-tracker` | Telegram+微信 |
| 14:00 | 🔄 Hermes 自动更新 + gateway/cron 健康检查 | systemd user timer | local 日志 |
| 16:10 | 🇭🇰 中港股收盘日报 | `cnhk-stock-tracker` | Telegram+微信 |
| 22:00 | 🗾 Yahoo JP 锐评日报 | `yahoo-jp-roast` | Telegram+微信 |
| 23:00 | 💾 Hermes 每日全量备份 | `hermes-snapshot` | local 静默 |
| */30 | 🧭 Cron 投递策略守卫 | `cron-multi-platform-delivery` | local 静默 |

内容任务通过 cronjob 单任务直投 Telegram+微信：目标配置为 `deliver='telegram:[REDACTED],weixin:[REDACTED]'`，后台守卫每 30 分钟执行 drift 审计；一次性/时间戳 schedule、缺失真实 target、系统维护任务 local-only 例外都由 `cron-multi-platform-delivery/scripts/delivery_policy.py` 审计。系统维护任务（如 Fedora 软件包每日更新、Hermes 每日全量备份、投递策略守卫）使用 `deliver=local` 静默执行。QQ/qqbot 仍不启用。

## 本次全仓扫描结论（代码化候选）

本仓库维护时优先把重复业务规则从 prompt/文档迁入脚本、审计器或单元测试，避免 cron 与报告格式再次漂移。当前已代码化的守门项包括：

- `scripts/skills_audit.py`：AST 语法检查、Markdown 投递目标脱敏检查、Yahoo JP no-agent 安全日报契约检查、README/GitHub workflow skill inventory 审计；
- `cron-multi-platform-delivery/scripts/delivery_policy.py`：内容任务 Telegram+微信双投递、维护任务 `local` 静默、一次性/时间戳任务排除，以及缺失真实 target 时 fail-closed 的投递策略审计；
- `yahoo-jp-roast/scripts/yahoo_rules.py`：体育过滤词与 allowlist 单源化，手动脚本和 no-agent 安全日报共用同一规则；
- `yahoo-jp-roast/scripts/safe_daily_report.py` / `send_safe_daily_items.py`：pickup 去重、自动扩页直到满足 20 条非体育新闻，不足则失败而不是投递低质量日报；每条原文 URL 契约与 JST 标题/归档日期已纳入回归测试；
- `5ch-roast/scripts/gen_report.py`：默认禁止“AI 锐评待补”骨架和不足 20 条的半成品报告出货，除非显式 `--allow-skeleton` / `--allow-partial`；
- `flight-search/scripts/flight_search.py` 与 `tests/test_flight_search.py`：城市/机场别名→IATA、往返总价/单航段展示分离、价格 deep link 来源输出、去程/返程报价方向匹配，以及直飞不变量（Amadeus `nonStop=true`、Kiwi `max_stopovers=0`，并过滤 provider 返回的中转航线）；
- `anison-live-countdown/scripts/common.py`、`scrape_bangdream.py`、`scrape_lovelive.py` 与 `anison-live-countdown/tests/test_official_sources.py`：多日巡回日期拆分、默认日期 JST today、`〜/～` 范围补齐（含跨年范围）、跨 today 多日过滤、BanG Dream 同域详情页日期 fallback、BanG Dream/LoveLive 官方 URL 表回归测试；
- `kaikatsu-club-vacancy/scripts/kaikatsu_vacancy.py` 与 `kaikatsu-club-vacancy/tests/test_kaikatsu_vacancy.py`：Nominatim 多候选评分、站/机场候选优先、店铺坐标缓存完整性阈值；
- `update-fedora-packages/scripts/update_fedora_packages.sh` 与 `update-fedora-packages/tests/test_update_fedora_packages.py`：Fedora 更新流程脚本化，cron 不再从 prompt 重建 `dnf5`/`dnf`/`sudo -n` 命令，dry-run 验证防回归；
- `tests/test_news_roast.py`、`tests/test_stock_trackers.py`、`cron-multi-platform-delivery/tests/test_delivery_policy.py`：Yahoo safe/per-item/JST/legacy debug、5ch fail-closed、中港/美股 ticker strip、中港混合市场休市文案、cron recurring 判定等回归测试；
- `stock-deep-analysis/scripts/lib/cache.py`、`pipeline/*`、`assemble_report.py`、`score_fns.py` 与对应 targeted tests：v3 pipeline 已把 `6_fund_holders`、`20_valuation_models` / `21_research_workflow` / `22_deep_methods` 纳入 24 个报告维度，并验证 dim labels / required key 常量、`score_dimensions` 输出、报告渲染 metadata 与缓存根目录全部一致；`agent_analysis` schema 保持宽松，只对结构/类型/过短内容告警，不承诺强制 `dim_commentary` 全维覆盖；auto-generated stub persona 现在默认封顶在 bullish 阈值以下，除非 reality_check/真实持仓覆盖；`total_funds_holding` 等基金数量字段不得再当百分比展示。

后续仍值得继续代码化的业务逻辑：

1. `update-fedora-packages`：后续可接入 cron 日志解析与失败告警阈值；dnf5/dnf/sudo -n 主流程已落成固定脚本与 dry-run 测试；
2. 运行中的 cron job inventory（例如工作仓库 issue watcher、备份任务状态）属于 live 配置漂移，需用 `cronjob list` / 投递策略脚本定期复核，不应只依赖 README 静态结论。

### 2026-05-18 全仓审查发现（第一批与第二批已处理）

本节记录 2026-05-18 全仓审查的复核结论、第一批/第二批修复状态与仍需持续复核的边界，避免 README 只保留“已代码化”结论而掩盖真实边界。所有公开文档继续使用脱敏投递目标，不写入真实 Telegram / 微信 ID。

**P1 · 第一批已修复 / 已验证**

1. `cron-multi-platform-delivery/scripts/delivery_policy.py` 已补 schedule classifier：cron 表达式 / `every ...` / `30m` 视为 recurring，ISO timestamp / 一次性时间不作为 recurring 守卫目标；`is_active_recurring_job()` 对应回归测试已覆盖。
2. `delivery_policy.py` 已改为 live/strict 路径缺少真实 `HERMES_DELIVERY_*` env 或 `~/.hermes/secrets/cron_delivery_targets.json` 时 fail closed；dummy target 仅允许测试显式传参使用。
3. live Hermes cron inventory 已通过 `cronjob list` 复核并纠偏；这类 live 配置仍需持续依赖守卫与 `delivery_policy.py ~/.hermes/cron/jobs.json`，不能只看 README 静态结论。
4. `yahoo-jp-roast/scripts/send_safe_daily_items.py` 已调整为先渲染 aggregate + per-item messages 并统一 forbidden marker 校验，再写所有 archive，避免污染归档。
5. Yahoo JP safe / per-item 报告已强制每条都有 `原文` URL；缺 `articleUrl` 的候选不会静默生成只含 Pickup 的条目。
6. `anison-live-countdown/scripts/scrape_lovelive.py` / `common.py` 已补 `〜/～` 范围日期拆分与逐日 `date >= today` 过滤，避免“昨天+今天”的 live 漏掉今天。
7. `anison-live-countdown/scripts/scrape_bangdream.py` 已补列表页缺日期时的同域详情页日期 fallback，并强制 URL 域名校验、UA/Referer/no proxy；会场缺失仍保守标记为「未定」。
8. `stock-deep-analysis/scripts/lib/agent_analysis_validator.py` 已确认维持宽松 schema：`REQUIRED_DIM_KEYS` 锁定 v3 registry 的 24 个报告维度覆盖（含 `6_fund_holders`），`validate({'agent_reviewed': True})` 不因缺少 `dim_commentary` 全维覆盖而失败。README 已改为保守表述，不再把它描述成强制全维 schema gate。

**P2 · 第二批已修复 / 已验证**

1. `cnhk-stock-tracker/scripts/snapshot.py` 已从 `http://hq.sinajs.cn/...` 改为 HTTPS，并由 `tests/test_stock_trackers.py::test_cnhk_snapshot_uses_https_for_sina_endpoint` 锁定。
2. `us-stock-tracker` / `cnhk-stock-tracker` 已抽出 `_split_custom_tickers()`，统一对 `--tickers` 输入 `strip()` 后再分类，避免带空格时股票/指数误分类。
3. LoveLive JSON-LD 场地映射已优先走 `_map_ll_venue()`，fallback card 已提取并 `urljoin()` 详情页 href，不再只回填列表页；对应回归测试在 `anison-live-countdown/tests/test_common.py`。
4. `5ch-roast` 的 `scraper.py` / `filter_score.py` 已改为 fail-closed：curl 非零/空响应、热帖列表为空、缺 raw_data、全量过滤无候选均非零退出并避免写出误导性中间产物。
5. `yahoo-jp-roast/scripts/yahoo_full.py` 已标注 `DEBUG_ONLY = True`，改为 import-safe 的 legacy/debug helper，入口仅在 main guard 下读取本地缓存，并复用 `yahoo_rules.is_sports()`。
6. `safe_daily_report.py` / `send_safe_daily_items.py` 已统一使用 `ZoneInfo("Asia/Tokyo")` 的 `jst_date_key()` / `jst_now_label()`，标题与归档日期不再依赖本机时区。

### 第一批 / 第二批修复执行记录

第一批按 TDD/回归测试方式完成 Task 1-6；第二批继续按 RED-GREEN 修复 P2-1 至 P2-6。公共文档/测试继续只使用 REDACTED 或假 target，真实 Telegram / 微信 ID 不写入 Git。

- **Task 1 · cron recurring 判定与 fail-closed**：已补 ISO/一次性 schedule 排除、duration/cron recurring 判定、live target 缺失 fail-closed、错误信息脱敏；覆盖 `cron-multi-platform-delivery/tests/test_delivery_policy.py`。
- **Task 2 · live NetEase watcher 投递漂移**：已用 `cronjob list` 复核并纠偏 live inventory；仓库只记录策略与脱敏示例。
- **Task 3 · Yahoo per-item 安全脚本**：已将 forbidden marker preflight 前置到所有 archive 写入前，并强制 safe/per-item 条目必须有原文 URL；覆盖 `tests/test_news_roast.py`。
- **Task 4 · Anison 日期与详情页 fallback**：已补 LoveLive/公共日期解析的 `〜/～` 范围、跨 today 多日过滤、跨年范围补齐，以及 BanG Dream 同域详情页日期 fallback；覆盖 `anison-live-countdown/tests/*`。
- **Task 5 · stock-deep README 对齐**：本轮不触碰核心 validator，只把 README 改为宽松 schema 的保守表述；targeted stock-deep gate 通过。
- **Task 6 · README / SKILL.md 文档同步**：已同步 Anison URL 表、BanG Dream HTTP 直取与日期 fallback 边界、Yahoo browser retry 契约、cron 守卫/审计边界与公共 target 脱敏规则。
- **P2-1/2 · stock tracker endpoint 与 `--tickers`**：`cnhk` 新浪端点改 HTTPS；US/CNHK daily/snapshot 的自定义 ticker 解析统一 trim 空白后分类。
- **P2-3 · LoveLive fallback**：JSON-LD 场地优先走 LoveLive 专用映射；fallback card 保留详情页 href，避免来源链接退化为列表页。
- **P2-4 · 5ch fail-closed**：抓取空结果、curl 失败、缺 raw_data、无候选均非零退出，不再写出看似成功的空产物。
- **P2-5 · Yahoo legacy helper**：`yahoo_full.py` 改为 DEBUG_ONLY/import-safe，使用 main guard 与 `yahoo_rules.is_sports()`。
- **P2-6 · Yahoo JST**：safe/per-item 报告标题与归档文件名统一基于 Asia/Tokyo，不依赖运行机器本地时区。

**第一批完成定义 / 本轮 gate**

- `git diff --check` 通过；
- `python3 scripts/skills_audit.py .` 通过；
- `python3 -m pytest tests shared/tests anison-live-countdown/tests cron-multi-platform-delivery/tests kaikatsu-club-vacancy/tests update-fedora-packages/tests -q` 通过；
- `python3 -m pytest tests/test_flight_search.py -q` 通过；
- README 推荐 stock-deep targeted gate 通过；
- `delivery_policy.py ~/.hermes/cron/jobs.json` 对 live jobs 通过；
- `git diff --name-only` 不包含非计划文件，且敏感信息扫描不包含真实 Telegram / 微信投递 ID。

### 2026-05-19 主干合入与 README 同步

P1/P2 修复与审计加固已通过受保护分支流程合入默认主干 `main`（仓库没有远端 `master` 分支）。合入采用 PR + CI + squash merge，不直接 push 受保护主干。

- **合入记录**：PR #10，squash 后主干 commit `f577878b2e5beb50597f629ccaba9c14ae0ef897`；
- **CI gate**：GitHub Actions / CodeQL / Skill repo audit / Code Review Doctor 全部通过；主测试集记录为 140 passed；
- **安全边界**：公开仓库仍只保留 `telegram:[REDACTED],weixin:[REDACTED]`；`delivery_policy.py` 的 audit / error 输出也必须脱敏，不回显 Telegram display name、数字 ID 或微信 OpenID；
- **README inventory**：常规技能数量以 `scripts/skills_audit.py` 的顶层 `*/SKILL.md` 清单为准，当前常规维护 13 个；大型独立 `stock-deep-analysis/` 单独说明且默认从常规审计中排除。README 数量、技能清单或 workflow inventory 漂移时，审计会失败。

### 2026-05-20 PR #12 · stock-deep 契约 / 缓存与中港休市文案修复

PR #12 已通过 GitHub Actions / CodeQL / Skill repository checks 后 squash 合入 `main`，主干 commit `3a052059a749f1ea4923acafe7753e053cfa3bb6`。合入后已将 `cnhk-stock-tracker/` 与 `stock-deep-analysis/` 从 repo 同步到 runtime skills，并通过 runtime diff / import smoke / AST 复核。

- **stock-deep 24 维契约**：`6_fund_holders` 与 `6_research` 明确分列，`score_dimensions`、报告 renderer metadata、dim labels、required-key 常量与文档全部对齐到 24 个报告维度；旧维度数量和旧投资者人数文案进入回归扫描。
- **投资者面板事实**：当前面板为 51 位投资者，其中 F 组游资 23 位；预览和报告百分比使用实际面板长度动态计算，不再使用旧固定人数分母硬编码。
- **基金持仓语义**：`total_funds_holding` / `funds_holding_count` 只表示基金数量（只），`fund_holding_pct` / `total_holding_pct` 才能作为百分比；回归测试锁定不会再渲染 `993.0%` 这类错误标签。
- **缓存隔离**：`stock-deep-analysis` 的 pipeline、legacy helper、network preflight、hottrend/news provider 与测试均改为 `UZI_CACHE_DIR` / `lib.cache.CACHE_ROOT`，pytest 默认把缓存重定向到 `/tmp`，避免仓库内 `.cache` 污染。
- **中港混合市场文案**：`cnhk-stock-tracker` 保留请求市场范围，A 股 / 港股分别判断休市与数据问题；单边休市不会误写成整体休市，expected-open 市场数据缺失不会被正常报告静默掩盖。

PR #12 合入前验证记录：stock-deep core contract/cache focused tests 17 passed、cache legacy focused tests 41 passed、`tests/test_stock_trackers.py` 12 passed、`scripts/skills_audit.py` 通过、`git diff --check` 通过、changed Python AST `checked=35 errors=0`、changed-file security scan `finding_count=0`、独立 review 通过。完整 stock-deep suite 仍可能受 `akshare` / `baostock` / `pandas` 可选依赖与历史 upstream-root 假设影响，需与本轮 targeted gate 区分。

## 本地校验

推荐在提交前运行：

```bash
cd ~/gemili-skills
PYTHONDONTWRITEBYTECODE=1 python3 scripts/skills_audit.py .
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests shared/tests anison-live-countdown/tests cron-multi-platform-delivery/tests kaikatsu-club-vacancy/tests update-fedora-packages/tests -q
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_flight_search.py tests/test_stock_trackers.py -q

cd ~/gemili-skills/stock-deep-analysis
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  scripts/tests/test_no_regressions.py::test_cache_root_can_be_redirected_out_of_repo \
  scripts/tests/test_no_regressions.py::test_pytest_default_cache_root_is_outside_repo \
  scripts/tests/test_no_regressions.py::test_pipeline_cache_paths_use_configurable_cache_root \
  scripts/tests/test_no_regressions.py::test_dim_labels_covers_all_24_report_dims \
  scripts/tests/test_no_regressions.py::test_dim_labels_cover_pipeline_registry \
  scripts/tests/test_no_regressions.py::test_agent_analysis_required_dim_keys_cover_registry_dims \
  scripts/tests/test_no_regressions.py::test_score_dimensions_outputs_all_24_report_dims \
  scripts/tests/test_no_regressions.py::test_assemble_report_renders_all_24_report_dims \
  scripts/tests/test_no_regressions.py::test_fund_holder_count_is_not_treated_as_holding_percentage \
  -q
PYTHONDONTWRITEBYTECODE=1 STOCK_NO_CACHE=1 python3 - <<'PY'
import sys
sys.path.insert(0, 'scripts')
import assemble_report
print('assemble_report import ok')
PY

cd ~/gemili-skills
git diff --check
```

`stock-deep-analysis/` 较大且包含 `akshare` / `baostock` / `pandas` / 浏览器等可选依赖与历史路径约束；常规仓库维护仍跑上面的 targeted stock-deep gate，完整 stock-deep suite 仅在维护该模块并准备好依赖时运行。
