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

Cron 投递目标策略已代码化为审计器：所有启用中的 recurring **内容任务**应使用 Telegram+微信双投递（`deliver='telegram:[REDACTED],weixin:[REDACTED]'`）；后台 `Cron投递策略守卫` 每 30 分钟静默审计，目标是不再使用「1 主 + N 转发器」。一次性/时间戳任务识别、缺失 secret 时 fail-closed、live inventory 复核都由策略脚本和运行时配置共同负责；真实 Telegram / 微信 target 仍只能来自环境变量、本机私密文件或运行时配置，不能写入 Git。

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

## 质量守门

本仓库维护时优先把重复业务规则从 prompt/文档迁入脚本、审计器或单元测试，避免 cron、报告格式与 skill 清单漂移。当前主要守门项包括：

- `scripts/skills_audit.py`：AST 语法检查、Markdown 投递目标脱敏、Yahoo JP no-agent 安全日报契约、README/GitHub workflow skill inventory、不要使用 `repeat='forever'` 等离线审计；
- `cron-multi-platform-delivery/scripts/delivery_policy.py`：内容任务 Telegram+微信双投递、维护任务 `local` 静默、一次性/时间戳任务排除，以及缺少真实 target 时 fail-closed 的投递策略审计；
- `tests/` 与各 skill 自带 `tests/`：覆盖 Yahoo safe/per-item/JST、5ch fail-closed、航班直飞不变量、中港/美股 ticker strip、LoveLive/BanG Dream 日期拆分、快活CLUB 坐标缓存、Fedora dry-run 等关键回归；
- `stock-deep-analysis/scripts/tests/`：面向大型独立模块的 targeted gates，锁定 24 个报告维度、51 位投资者、基金持仓字段语义、cache root、报告渲染 metadata 与 self-review 机制。

运行中的 cron job inventory、真实投递 target、备份状态等属于 live 配置漂移，仍需用运行时命令和 `delivery_policy.py` 定期复核；README 只记录源码契约与脱敏示例。

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
