# Gemili Skills

Hermes / Codex Agent skills source repo. 当前常规维护 **13 个 skill**，另有大型独立 `stock-deep-analysis`；仓库共包含 14 个顶层 `SKILL.md`。内容覆盖行情追踪、新闻报告、旅行查询、系统维护、备份和仓库开发准则。

运行时目录由宿主环境决定；Codex 通常安装到 `$CODEX_HOME/skills`，旧 Hermes 环境可能使用 `~/.hermes/skills`。本仓库只保存可版本管理的源码和测试，不提交真实投递目标、密钥或备份产物。

## 安装

推荐用 Codex 的 `skill-installer` 从本仓库安装。手动安装时，把需要的顶层 skill 目录复制到运行时 skills 目录即可；每个可安装目录都包含自己的 `SKILL.md`。

```bash
git clone https://github.com/TzeHimSung/gemili-skills.git ~/gemili-skills
```

## Skills

| Skill | 用途 |
| --- | --- |
| `shared` | 股票类 skill 共用 Python 库，提供行情数据结构、HTTP 客户端、市场状态和趋势分析。 |
| `us-stock-tracker` | 美股行情追踪，使用新浪实时快照与 Yahoo v8 收盘数据生成盘中/盘后报告。 |
| `cnhk-stock-tracker` | 中港股行情追踪，覆盖 A 股芯片半导体与港股科技 / LLM 概念。 |
| `stock-deep-analysis` | 个股深度分析工作流，生成多维研究、投资者评审、估值建模和 HTML 报告。 |
| `anison-live-countdown` | LoveLive! / BanG Dream! 未来一年 live 活动倒计时报表。 |
| `5ch-roast` | 抓取 5ch.io 实时热帖并生成中日双语锐评报告。 |
| `yahoo-jp-news-scraper` | Yahoo Japan News 热榜、正文和评论 AI 要約的底层抓取能力。 |
| `yahoo-jp-roast` | Yahoo JP 热榜中文锐评日报，筛除体育新闻并归档输出。 |
| `kaikatsu-club-vacancy` | 查询日本快活CLUB 最近三家门店的官网实时空席。 |
| `flight-search` | 查询直飞航班时刻、机场/航站楼、机型、可选价格来源和验证链接。 |
| `cron-multi-platform-delivery` | 审计 cron 投递策略，确保内容任务走 Telegram+微信，QQ 仍不可用。 |
| `update-fedora-packages` | Fedora / WSL 后台软件包更新，非交互执行并避免等待 sudo 密码。 |
| `hermes-snapshot` | Hermes 全量备份封装，生成本地备份、加密产物和轻量 manifest。 |
| `repo-development-guidelines` | 仓库开发 guardrail，要求分支隔离、计划、测试/校验和审慎收尾。 |

各 skill 的触发条件、脚本入口、数据源约束和运行细节以对应目录的 `SKILL.md` 为准。

## 仓库结构

```text
gemili-skills/
├── <skill-name>/SKILL.md       # 可安装 skill
├── <skill-name>/scripts/       # skill 自带脚本
├── <skill-name>/tests/         # skill 自带测试
├── shared/                     # 共用 Python 包
├── scripts/skills_audit.py     # 仓库级离线审计
└── tests/                      # 跨 skill 回归测试
```

## 维护约定

- README 只保留入口信息和稳定约定；运行中的 cron inventory、投递目标、备份状态和历史变更不写在这里。
- 真实 Telegram / 微信 target、token、cookie、备份 zip/gpg 等只允许来自本机私密配置或运行时环境，不提交到 Git。
- 行为变化优先补测试；文档变化至少跑仓库审计和 `git diff --check`。
- 大型模块 `stock-deep-analysis/` 的完整依赖较重，日常维护优先跑它的 targeted no-regression gate。

## 本地校验

推荐在提交前运行：

```bash
cd ~/gemili-skills
PYTHONDONTWRITEBYTECODE=1 python3 scripts/skills_audit.py .
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests shared/tests anison-live-countdown/tests cron-multi-platform-delivery/tests kaikatsu-club-vacancy/tests update-fedora-packages/tests -q
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_flight_search.py tests/test_stock_trackers.py -q
git diff --check
```

如果改到 `stock-deep-analysis/`，再按该 skill 的 `SKILL.md` 运行 targeted gate。
