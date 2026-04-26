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

### 阶段 1：获取热榜列表
1. `browser_navigate` → https://news.yahoo.co.jp/topics/top-picks
2. `browser_console` 执行 JS 提取前25条 pickup IDs 和标题

### 阶段 2：批量提取元数据（curl）
```python
for pid in pickup_ids:
    curl pickup page → 提取 article_id（正则 /articles/([a-f0-9]+)/comments）
    → 提取 meta description
    → 判断类别（标题含 阪神/マラソン/有原/新庄 等标记为体育→跳过）
```

### 阶段 3：获取评论 AI 摘要（delegate_task + browser）
- 仅处理非体育类且有评论的文章
- delegate_task(browser, 3并发) → 提取「ヤフコメAI要約」
- フォーカストピック + 主なヤフコメ + 関連ワード + コメント数

### 阶段 4：输出中文锐评报告
格式：
```
### #N 标题 💬N件
📝 正文：[中文总结]
💬 评论：[风向+AI摘要]
🔍 锐评：[毒舌吐槽，120-150字]
```

## 体育类过滤词
标题含以下任一关键词则跳过：
阪神、タイガース、マラソン、新庄、有原、近本、甲子園、セ・リーグ、パ・リーグ、日本ハム、サッカー、Jリーグ、大相撲、プロ野球

但以下不算体育：
東方神起（演唱会）、フワちゃん（艺人）

## 已知问题
- curl 静态 HTML 不含评论数（JS 渲染），需 browser
- 部分 /articles 页面 404，但 pickup 页可访问
- 政治敏感话题常被关评或删页

## 输出
- 对话中直接发送 Markdown 锐评报告
- 存档：~/.hermes/yahoo-reports/YYYY-MM-DD-roast.md
