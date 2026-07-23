---
name: anison-live-countdown
description: 生成 LoveLive / BanG Dream 未来一年 live 活动倒计时报表。当前只展示 BanG Dream! 与 LoveLive!，不展示偶像大师。
---

# 偶像企划 Live 倒计时报表

## 快速使用

```bash
# 一键执行（爬取 + 生成报表）
python3 scripts/run_all.py

# 仅用已有数据重新生成报表
python3 scripts/run_all.py --skip-scrape

# 单独运行某个爬虫
python3 scripts/scrape_bangdream.py [data/]
python3 scripts/scrape_lovelive.py [data/]

# 单独生成报表
python3 scripts/generate_report.py [data/] -p general   # 通用完整表
python3 scripts/generate_report.py [data/] -p telegram  # Telegram
python3 scripts/generate_report.py [data/] -p weixin    # 微信单条摘要
```

## 文件结构

```
scripts/
  common.py              # 公共库：HTTP客户端、日期解析、场地映射
  scrape_bangdream.py    # BanG Dream! 官方站爬虫
  scrape_lovelive.py     # LoveLive! 系列爬虫（蓮ノ空/Liella!/虹ヶ咲/Aqours/μ's）
  generate_report.py     # 报表生成器（合并 JSON → markdown）
  run_all.py             # 一键入口
data/
  bandori.json           # BanG Dream 抓取结果
  lovelive.json          # LoveLive 抓取结果
  report.md              # 通用完整报表
  report_telegram.md     # Telegram 兼容版报表
  report_weixin.md       # 微信单条摘要（每企划最近 5 场）
```

## 覆盖企划

当前日报只展示以下两类；偶像大师已按用户偏好停用。

### BanG Dream! 系列
Poppin'Party / Roselia / RAISE A SUILEN / Morfonica / MyGO!!!!! / Ave Mujica / 夢限大みゅーたいぷ

### LoveLive! 系列
蓮ノ空女学院 / Liella! / 虹ヶ咲学園 / Aqours / μ's


---

## 数据源状态

| 数据源 | 状态 | 方式 | 备注 |
|--------|------|------|------|
| bang-dream.com/events/ | ✅ | Python requests + regex | HTML 静态渲染；列表缺日期时会抓取同域详情页日期 fallback；多日巡回自动拆分 |
| lovelive-anime.jp/*/{live,live-event,news}/ | ⚠️ | Python requests + regex | 各系列 URL 不统一；支持 `〜/～` 范围、跨 today 多日过滤与多策略兜底 |

LoveLive JSON-LD 路径需优先使用 `_map_ll_venue()`，避免通用 `map_venue()` 把「ベルーナドーム」粗略映射成西武ドーム；fallback card 解析必须提取 `<a href>` 并用 `urljoin()` 存为 `detail_link`，不要只回填列表页 URL。

---

## ⚠️ 关键环境约束

本服务器环境只能用 Python requests：

```python
import requests

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "ja-JP,ja;q=0.9",
    "Referer": "<source_url>",  # ⚠️ 必带
}
r = requests.get(url, headers=headers, timeout=15,
                 proxies={"http": None, "https": None})
```

### 已确认失败的所有替代方案
- ❌ yfinance / Yahoo Finance：IP 全封 429
- ❌ browser_navigate：CDP 超时 / Bot 检测
- ❌ DuckDuckGo Lite：Network unreachable
- ❌ 东方财富：代理 SSL 不稳定
- ❌ curl 大批量：输出截断 + SSL 代理错误

---

## 报表规则

| 倒计时 | 标记 | 说明 |
|--------|------|------|
| <0 天 | 不展示 | 已结束活动不会进入推送报表 |
| 0 天 | "今天!" | 当天活动 |
| 1-3 天 | 🔴 | 紧急 |
| 4-7 天 | 🔥 **粗体** | 临近 |
| 8-30 天 | ⏳ | 关注 |
| >30 天 | 📅 | 未来 |

- 艺人最多显示 2 名，超过加 `+N`
- 活动名截断到 50 字（由 `generate_report.py` 控制），如果事件带 `detail_link`/`url`，标题必须渲染成 Markdown 链接
- フェス/合同イベント标记 🎪
- **多日巡回必须拆分**（最易漏的 bug）：`〜/～` 范围要补齐中间日期，范围终点不能消耗下一场 venue slot；换行分隔符不能丢，否则会导致 venue 错位。
- **推送报表必须过滤已结束 live**：`generate_report.py` 只展示 `date >= today` 的活动，不再保留过去 7 天“已结束”行
- **通用版与 Telegram 使用 Markdown 表格**：每个表格最多 20 条记录；同一企划超过 20 条时按 `第X/Y页` 拆成多个表格，避免移动端长表错位。
- **微信使用紧凑单条摘要**：BanG Dream! 与 LoveLive! 各保留最近 5 场，不含长链接，格式化前不超过 1800 字；完整活动表继续发送到 Telegram 并保留本地归档。
- Telegram 版额外清洗 `「」` `｜`；会保留 Markdown 表格分隔线和独立 `---` 分割线

---

## ⚠️ 已知坑点（修改代码前必读）

### 蓮ノ空页面结构
页面使用 `<div class="list__inner"><ul><li>...` 结构，每个 `<li>` 内有精确字段：
- `class="live_title"` → `<p>` 标题
- `class="live_date"` → `<span>` 日期（支持 `＜Stage／Date＞` 多阶段格式）
- `class="live_place"` → `<span>` 场地（同上多阶段格式）

专用解析器：`_parse_hasunosora_page()` in `scrape_lovelive.py`。

### 半角/全角括号陷阱
蓮ノ空页面的 `＜Stage／Date＞` 格式中，**开头 `＜` 是全角，结尾 `>` 是半角**，不对称。
错误正则：`＜([^＞]+)／([^＞]+)＞` — `[^＞]` 不会排除半角 `>`，且 `＞` 匹配不到半角 `>`。
正确正则：`＜([^／]+)／([^＞>\n]+)[＞>]?`

### 日期简写层级
日文日期省略有三种：
1. `2026年5月2日(土)` — 完整，直接解析
2. `5月3日(日)` — 省略年份，需补 year → `f"{year}年5月3日"`
3. `15日(日)` — 仅剩日，需补 year+month → `f"{year}年{month}月15日"`

`split_tour_dates()` 在 `common.py` 已处理三种情况，并支持 `2026年5月2日(土)〜4日(月)`、`2026年12月31日(水)〜1月2日(金)` 这类范围补齐；范围内所有日期沿用起始 venue，后续非范围日期才前进到下一个 venue。

### LoveLive 各系列 URL 差异
| 系列 | 正确 URL | 错误 URL |
|------|----------|----------|
| 蓮ノ空 | `hasunosora/live-event/` | — |
| Liella! | `yuigaoka/live/` | ~~`yuigaoka/news/`~~（旧文档路径，不是默认日报源）；~~`liella/live-event/`~~ (404) |
| 虹ヶ咲 | `nijigasaki/live-event/` | ~~`nijigasaki/news/`~~ (200 但无数据) |
| Aqours | `uranohoshi/live/` | ~~`uranohoshi/news/`~~（旧文档路径，不是默认日报源）；~~`aqours/news/`~~ (404) |
| μ's | `news/` | μ's 没有独立 `live-event/` 默认源，需从全站 news 过滤 live/event |

LoveLive fallback 解析若列表 card 中存在详情页链接，`detail_link` 必须指向该详情页；JSON-LD Event 的 `location.name` 要走 LoveLive 专用场地映射后再入库。对应回归测试：`anison-live-countdown/tests/test_common.py::test_lovelive_jsonld_uses_lovelive_specific_venue_mapping` 与 `::test_lovelive_card_fallback_keeps_detail_href`。

### BanG Dream! 详情页 fallback
列表页 card 若缺日期，`scrape_bangdream.py` 会只跟进 `bang-dream.com` 同域详情页并提取可解析日期（如 `日程` / `開催日` / `開催日時`）。当前 fallback 不从详情页补会场；列表页会场缺失时仍应保守标记「未定」。不要抓取外部绝对链接；详情页请求必须带 UA/Referer 且禁代理，避免官网浏览器 Bot 检测 404。

### 垃圾标题过滤
`_is_garbage_title()` 过滤：JS 代码 (`function(`)、CSS (`@media`)、HTML 残留、页面导航 (`LIVE & EVENT`)、纯标点、短于 4 字符。
`is_non_live_keyword()` 过滤：舞台挨拶、上映会、配信、グッズ等。

---

## 注意事项

- `proxies={"http": None, "https": None}` 必须设置，否则走代理 429
- `Referer` header 必须带，否则被拒
- 日本曜日表記：月火水木金土日
- 未確認の会場は「未定」と明記
- 默认日报不抓取、不展示偶像大师；即使 `data/idolmaster.json` 残留，`generate_report.py` 也必须忽略。
- 日期过滤以 `common.jst_today()` 为准；跨时区运行时不要用本机 naive `date.today()` 替代。
- Telegram 表格避免 `「」` `｜`；不要把表格分隔线或独立 `---` 当成需要删除的内容
- Cron 静默失败时检查 session 文件是否只有 todo list
