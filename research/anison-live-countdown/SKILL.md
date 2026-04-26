---
name: anison-live-countdown
description: 生成 LoveLive / BanG Dream / 偶像大师 未来一年 live 活动倒计时报表。覆盖三大企划全系列，数据来源交叉验证官网+购票站。
---

# 偶像企划 Live 倒计时报表

## 覆盖企划

### LoveLive! 系列
- μ's / Aqours / 虹ヶ咲学園 / Liella! / 蓮ノ空女学院 / その他

### BanG Dream! 系列
- Poppin'Party / Roselia / RAISE A SUILEN / Morfonica / MyGO!!!!! / Ave Mujica / 夢限大みゅーたいぷ

### 偶像大师 系列
- 765AS / シンデレラガールズ / MILLION LIVE! / SideM / シャイニーカラーズ / 学園アイマス

---

## ⚡ 核心执行规则

### 必须使用 Python + requests（非 curl、非浏览器）

本环境 `execute_code` 中 Python requests 最可靠。关键参数：
- **Headers 必带 `Referer`**：否则被拒
- **必须绕过代理**：`proxies={'http': None, 'https': None}`
- **timeout=15**

```python
import requests, re
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'ja-JP,ja;q=0.9',
    'Referer': 'https://bang-dream.com/events/'  # ⚠️ 必带
}
r = requests.get(url, headers=headers, timeout=15, proxies={'http': None, 'https': None})
```

### ❌ 禁止的方案（全部失败过）
- ❌ yfinance / Yahoo Finance：IP 被封
- ❌ browser_navigate：CDP 超时 / Bot 检测
- ❌ curl 大批量：输出截断 + SSL 代理错误
- ❌ DuckDuckGo Lite：Network unreachable
- ❌ 东方财富 eastmoney：代理 SSL 不稳定
- ❌ Google Finance / MarketWatch：反爬

---

## 数据采集流程

### Step 1：BanG Dream 官方站（✅ 最可靠）

**已验证可行：Python requests 直取 + regex 解析**

```python
import requests, re
from datetime import date

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'ja-JP,ja;q=0.9'
}
today = date.today()

r = requests.get('https://bang-dream.com/events/', headers=headers, timeout=15,
                 proxies={'http': None, 'https': None})
html = r.text

# 提取文章块 — 已验证的 regex 模式
articles = re.findall(r'<article class="p-live-event-list__item">(.*?)</article>', html, re.DOTALL)

events = []
for art in articles:
    # 标题
    title_m = re.search(r'p-live-event-list__item-title"[^>]*>(.*?)</div>', art)
    title = title_m.group(1).strip() if title_m else "?"
    title = re.sub(r'<[^>]+>', '', title).replace('&#039;', "'")
    
    # 日期（⚠️ 多日巡回格式：「2026年4月17日(金)・4月26日(日)・5月1日(金)...」）
    date_block = re.search(r'p-live-event-list__item-date.*?<p>(.*?)</p>', art, re.DOTALL)
    date_text = date_block.group(1).strip() if date_block else "?"
    date_text = re.sub(r'<[^>]+>', '', date_text)
    
    # 场地（⚠️ 对应多日巡回：「Zepp Fukuoka、Zepp Namba、Zepp Nagoya...」）
    venue_m = re.search(r'p-live-event-list__item-place.*?<p>(.*?)</p>', art, re.DOTALL)
    venue = venue_m.group(1).strip() if venue_m else "?"
    venue = re.sub(r'<[^>]+>', '', venue)
    
    # 艺人
    artists = re.findall(r'p-live-event-list__item-artist-item"[^>]*>(.*?)</span>', art)
    
    # 类别（ライブ/イベント/フェス）
    cat_m = re.search(r'p-live-event-list__item-category.*?<span>(.*?)</span>', art, re.DOTALL)
    category = cat_m.group(1).strip() if cat_m else "ライブ"
    
    events.append({
        "title": title, "date_text": date_text, "venue": venue,
        "artists": artists, "category": category
    })
```

**⚠️ 多日巡回拆分（关键！漏了会被用户指正）**

Ave Mujica TOUR 等巡回 event 的 `date_text` 包含多个日期（`・` 分隔），`venue` 包含多个场地（`、` 分隔）。必须按顺序一一映射：

```
date_text: "2026年4月17日(金)・4月26日(日)・5月1日(金)・5月4日(月)..."
venue:     "Zepp Fukuoka、Zepp Namba、Zepp Nagoya、Zepp Haneda..."
```

拆分逻辑：第一个日期带年份，后续省略年份沿用第一个的年份。

```python
def split_tour_dates(date_text, venue_text):
    dates = [d.strip() for d in date_text.split('・')]
    venues = [v.strip() for v in venue_text.split('、')]
    # 第一个日期补全年份
    result = []
    year = None
    for i, d in enumerate(dates):
        ym = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日', d)
        if ym:
            year = ym.group(1)
            result.append((d, venues[i] if i < len(venues) else '未定'))
        elif year:
            # 省略年份的后续日期，如 "4月26日(日)"
            m2 = re.match(r'(\d{1,2})月(\d{1,2})日', d)
            if m2:
                full_date = f"{year}年{m2.group(1)}月{m2.group(2)}日"
                result.append((full_date, venues[i] if i < len(venues) else '未定'))
    return result
```

**已验证的场地映射：**
| 场地 | 常见活动 |
|------|----------|
| 有明アリーナ | Roselia, Poppin'Party×Roselia |
| SGC HALL ARIAKE | Ave Mujica FINAL, RAS 東京, 夢限大 東京 |
| Zepp Namba | Ave Mujica 大阪 |
| Zepp Nagoya | Ave Mujica 名古屋 |
| Zepp Haneda | Ave Mujica 東京 |
| Zepp Fukuoka | Ave Mujica 福岡 |
| 神戸国際会館こくさいホール | RAS 兵庫 |
| 鴻巣市文化センター | MyGO 迷子集会 |
| ぴあアリーナMM（横浜） | MyGO!!!!! 9th LIVE, FLOW THE FESTIVAL |
| TACHIKAWA STAGE GARDEN | Morfonica |
| 國立體育大學綜合體育館（林口體育館） | Ave Mujica 台北 |
| 幕張メッセ | Animelo Summer Live |
| COOL JAPAN PARK OSAKA | MyGO 迷子集会 大阪 |

### Step 2：LoveLive 官方站

```python
# 蓮ノ空女学院 live-event 页面
r = requests.get('https://www.lovelive-anime.jp/hasunosora/live-event/',
    headers=headers, timeout=15, proxies={'http': None, 'https': None})

# ⚠️ 该站部分 JS 渲染，curl 只能拿到日期片段
# 提取日期：re.findall(r'(\d{4})[年/.](\d{1,2})[月/.](\d{1,2})', r.text)
# 提取标题需查看具体 HTML 结构
```

### Step 3：偶像大师官方站

⚠️ `/events/` 返回 404，正确路径是 `/live_event/`（200 OK）。
⚠️ 但该页面**完全 JS 渲染**，Python requests 也只能拿到空 HTML shell。

**已验证失败的所有方案：**
- `https://idolmaster-official.jp/events/` → 404
- `https://idolmaster-official.jp/live_event/` → 200，空 HTML（Python requests 也失败）
- `web_search` 工具 → 主 Agent 无此工具
- `delegate_task` 子 Agent → 只返回摘要，不返回实际搜索结果
- DDG lite → Network unreachable（IP 被封）

**唯一可用的替代方案：**
1. eplus 各ブランド artist ID（Step 4）— 但经常只有日期无名称
2. 各品牌既知の個別イベントページ直リンク（例：`/live_event/mr_idolworld2026/`）
3. 标注「現在データ取得不可」— 偶像大师的 live 日程本来公布得少，属于正常情况

### Step 4：eplus 购票站（JSON-LD 结构化数据）

eplus 内嵌 JSON-LD Event schema，是最可靠的第三方数据源：

```bash
curl -sL "https://eplus.jp/sf/word/<artist_id>" | python3 -c "
import sys,re,json
html=sys.stdin.read()
for m in re.findall(r'<script type=\"application/ld\+json\">(.*?)</script>', html, re.DOTALL):
    data=json.loads(m)
    # parse Event @type for dates, names, locations
"
```

**已确认 eplus artist ID：**
- ラブライブ！: 0000150880
- BanG Dream: 0000084669, 0000159108
- アイドルマスター: 0000031068, 0000126198

### Step 5：DuckDuckGo Lite（❌ 本环境不可用）

⚠️ 服务器无法连接 DDG（Network unreachable）。**跳过此步骤，使用内置 web_search 替代。**

---

## 报表生成规则

### 倒计时计算
```python
from datetime import date
today = date.today()
days = (event_date - today).days  # 负数 = 已过期，过滤掉
```

### 表格格式
- 日期简化：`4月26日`，不重复年份
- 倒计时标记：`<= 7天` → 🔥 **粗体**、`<= 30天` → ⏳、`> 30天` → 📅
- 艺人列最多显示 2 名，超过加 `+N`
- 活动名截断到 30 字
- フェス/合同イベント标记 🎪

### 月別分布
```python
months = {}
for e in all_events:
    m = e['date'].month
    months[m] = months.get(m, 0) + 1
# 用 █ 绘制条形图
```

### 数据源标注
只列出**实际成功访问**的 URL，404/失败的不要写。

---

## 已验证的數據源状态

| 数据源 | 状态 | 备注 |
|--------|------|------|
| bang-dream.com/events/ | ✅ 200 | HTML 静态渲染，regex 可解析 |
| lovelive-anime.jp/hasunosora/ | ⚠️ 200 | 部分 JS 渲染，日期可提取标题难 |
| idolmaster-official.jp/events/ | ❌ 404 | 正确路径是 /live_event/ |
| idolmaster-official.jp/live_event/ | ⚠️ 200 | 完全 JS 渲染，空 HTML shell |
| eplus.jp | 🔄 未测试 | JSON-LD 结构化数据 |
| lite.duckduckgo.com | ❌ unreachable | 本服务器无法连接 |

---

## 注意事项

- 倒计时は `(event_date - today).days`
- 日本曜日表記：月火水木金土日
- フェス/合同イベントは 🎪 で区別
- 未確認の会場は正直に「未定」
- **多日巡回は必ず拆分**（最も漏れやすいバグ）
- **今日のイベントを絶対に見落とさない**
- 偶像大师が取れない場合は「データ不可」と明記し、次回更新で再試行

## Telegram 表格渲染注意

Telegram 的 markdown parser 对以下字符敏感，报表中应避免：

- `「」` 书名号 → 去掉或用空格代替
- `｜` 全角竖线 → 用 `·` 或空格代替
- `---` 分隔线 → 用空行代替
- 活动名中的 `「Event」` 写成 `Event`
- 日期行中的 `｜` 写成 `·`

## 静默失败排查

Cron job 中复杂任务可能静默失败：session 文件只包含 todo list 就停了，state 显示 unknown，agent log 只有一行 startup。原因通常是：
- 模型 API 瞬时错误（deepseek reasoning_content 回传失败）
- 浏览器/Bot 检测超时
- 网络不可达静默吞错

缓解措施：
- 使用 `delegate_task` 并行化各企划搜索
- 保持 prompt 简洁、步骤明确
- 正式启用前先手动跑一次验证
