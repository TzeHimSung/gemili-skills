---
name: yahoo-jp-roast
description: 爬取 Yahoo!ニュース 热榜（top-picks），筛除体育类新闻，提取正文摘要+评论AI总结，输出中文深度锐评报告（每篇≥300字：正文→评论→毒舌点评），风格辛辣幽默。输出到对话+存档。
category: research
---

# Yahoo!ニュース 熱榜銳評

## 触发条件
- 「Yahoo日本热榜」「雅虎新闻锐评」「yahoo jp roast」等

## 风格定位
- **中文输出**，语气辛辣幽默，带吐槽属性
- 每篇 ≥300 字：正文总结 → 评论风向 → 毒舌点评
- **自动筛除体育类**（棒球、马拉松、足球等，但东方神起演唱会算娱乐保留）

## 工作流

### 一键运行
```bash
python3 ~/.hermes/skills/research/yahoo-jp-roast/scripts/yahoo_jp_roast.py --pages 3
```
自动爬取前3页→筛体育→按评论降序→分类输出带链接表格，并归档到 `~/.hermes/yahoo-reports/YYYY-MM-DD-roast.md`。

### 手动流程
1. `terminal`: `yahoo_jp_roast.py --pages 3` 内部用 curl 抓取 top-picks HTML → /tmp/yahoo_p{1,2,3}.html
2. Python解析: 从 `id` 后方匹配最近的 `commentCount`，并提取 `title` + `articleUrl`（静态 HTML 当前可取评论数）
3. 关键词筛除体育类
4. 按 `comment_count` 降序排列
5. 分类输出

### 阶段 2：批量提取元数据（curl）
```python
for pid in pickup_ids:
    curl pickup page → 提取 article_id（正则 /articles/([a-f0-9]+)/comments）
    → 提取 meta description
    → 判断类别（标题含 阪神/マラソン/有原/新庄 等标记为体育→跳过）
```

### 阶段 3：获取评论 AI 摘要及正文 (delegate_task + browser)
- 仅处理非体育类且有评论的文章。
- 使用 `delegate_task` 批量处理 (建议并发数不超过3)，每个子任务负责：
    1. 导航至评论页：提取「ヤフコメAI要約」。这通常需要通过 `browser_snapshot(full=True)` 获取完整页面内容，然后使用正则表达式或字符串匹配来解析。如果存在“もっと見る”按钮，必须先 `browser_click` 展开，再重新 `browser_snapshot(full=True)`。
    2. 导航至原文页：尝试提取文章主内容。同样需要 `browser_snapshot(full=True)`，并通过解析 HTML 结构 (如 `<p>` 标签内的文本) 来获取。注意过滤掉导航、广告、脚注等非正文内容。
    3. 如果文章存在多页，直接使用 `browser_click` 页码或“次へ”可能无法可靠地加载新内容，因为有些网站会动态更新而不改变 URL。此时，应尝试重新获取 `browser_snapshot` 并解析，或接受仅获取首页内容。
- 输出格式应为 JSON，包含 `ai_summary`、`article_body`、`retry_count`、`failure_reason` 字段。

#### AI 摘要失败重试策略（强制）
- 不允许因为第一次 `browser_snapshot` 未匹配就直接写「AI总结未成功提取，请参照评论链接」。
- 对每个有评论链接的非体育文章，`ai_summary` 为空时必须在同一轮任务内重试，最多 3 次：
  1. 重新 `browser_navigate` 到评论页，等待页面稳定后取 `browser_snapshot(full=True)`；
  2. 搜索并点击「もっと見る」「AI要約」「コメントをもっと見る」等可能展开摘要/评论的按钮，再取一次完整 snapshot；
  3. 用 `browser_console(expression='document.body.innerText')` 作为备用通道提取页面可见文本；
  4. 若单个子任务返回 `null`，对该 article URL 再派发一次 delegate/browser 子任务复核，避免单 worker 瞬时加载失败。
- 只有满足以下条件之一，才允许最终写「AI总结未成功提取」：
  - 评论页明确不存在「ヤフコメAI要約」或评论区关闭；
  - 3 次重试后仍因 CAPTCHA、连接错误、页面 404/删页、JS 未加载等失败；
  - 该新闻评论数为 0 或无评论链接。
- 最终报告若仍需保留失败占位，必须在内部记录 `failure_reason`；正文可简短写明「重试3次仍未取到（原因：…），请参照评论链接」，不要无原因地泛泛写失败。
- 同一 article URL 被多个 pickup 收录时，必须复用第一次成功的 `ai_summary/article_body`；如果第一次失败，后续重复条目要触发同一 URL 的复核，而不是复制失败占位。

## 内容提取常见问题 (Extraction Pitfalls)
- **动态内容加载**: 「ヤフコメAI要約」和文章正文可能由JavaScript动态加载，`curl` 无法获取，必须使用 `browser_navigate` 和 `browser_snapshot`。
- **“もっと見る”按钮**: 评论区常有“もっと見る”按钮展开AI摘要。需要 `browser_click`，但并非每次点击都能在 `browser_snapshot` 中立即反映内容更新。
- **分页文章**: 文章可能有多页。`browser_click` 页码或“次へ”后，URL 可能不变或页面内容未实际更新。需要仔细检查 `browser_snapshot` 来判断内容是否变化，否则可能只抓取到第一页内容。
- **CAPTCHA/连接错误**: 访问评论页或原文页时，可能会遇到 CAPTCHA 验证或 `net::ERR_CONNECTION_CLOSED` 错误，导致无法获取内容。
- **HTML结构变化**: Yahoo!新闻的HTML结构可能随时变化，导致现有解析逻辑失效。需要定期检查和更新JavaScript表达式或正则表达式。
- **AI摘要缺失**: 并非所有文章都有「ヤフコメAI要約」。但未找到不等于失败结束；必须按“AI 摘要失败重试策略”完成最多 3 次重试/复核后，才可报告为 `null`，并记录原因。
- **正文获取不完整**: 由于上述分页问题或复杂布局，可能无法获取文章的全部正文。

### 阶段 4：输出中文锐评报告
格式：
```
## #N 标题 — N💬
原文链接：
- Pickup: https://news.yahoo.co.jp/pickup/...
- 原文: https://news.yahoo.co.jp/articles/...
- 评论: https://news.yahoo.co.jp/articles/.../comments

📝 正文：[中文总结]
💬 评论：[风向+AI摘要]
🔍 锐评：[毒舌吐槽，120-180字]
```

报告正文要求：
- 不要在开头放 Top10/Top20 元数据汇总；评论数、pickup、原文链接等元数据随每条新闻展示，避免重复。
- 默认至少展示 20 条非体育热帖；若同一 article URL 被多个 pickup 收录，可合并为一条正文，但仍应说明对应 pickup。

## 体育类过滤词
标题含以下任一关键词则跳过：
阪神、タイガース、マラソン、新庄、有原、近本、甲子園、セ・リーグ、パ・リーグ、日本ハム、サッカー、Jリーグ、大相撲、プロ野球

但以下不算体育：
東方神起（演唱会）、フワちゃん（艺人）

## Cron/投递排障经验
- 若定时任务显示 `last_status=ok` 且 `last_delivery_error=null`，但用户反馈没收到，不能只看 cron 状态；必须读取 `~/.hermes/cron/output/<job_id>/YYYY-MM-DD_*.md` 确认最终正文是否真实生成。
- 若输出文件中只有 `API call failed after 3 retries`、`Prompt blocked due to safety` 等模型错误，说明任务触发和数据抓取可能正常，但最终生成被模型安全策略拦截；应改用已验证可用的 provider/model（例如先用 `hermes chat -Q --provider gemini -m gemini-2.5-flash -q '只回复 OK'` 探活，再用 `cronjob update` 固定该模型）。
- 修复 cron prompt 时要明确：最终回复必须是中文日报正文；只展示至少 20 条非体育新闻；不要投递脚本原始候选池、Top10/Top20 元数据汇总或超过 20 条的流水账。

## 已知问题
- top-picks 静态 HTML 当前含 `commentCount`；若 Yahoo 页面结构变化，脚本会非零退出并提示 source shape changed
- 「ヤフコメAI要約」仍需 browser/delegate_task 获取，curl 阶段只做热榜元数据
- 部分 /articles 页面 404，但 pickup 页可访问
- 政治敏感话题常被关评或删页
- 部分模型可能误判新闻内容/锐评生成涉及安全风险，导致最终回复被拦截；遇到时按上面的 Cron/投递排障流程验证输出文件、切换模型并手动重跑。

## 输出
- 对话中直接发送 Markdown 锐评报告
- 存档：~/.hermes/yahoo-reports/YYYY-MM-DD-roast.md
