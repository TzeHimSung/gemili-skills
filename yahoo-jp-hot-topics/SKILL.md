---
name: yahoo-jp-hot-topics
description: 爬取 Yahoo!ニュース 热榜（top-picks），提取每篇文章的正文摘要和评论 AI 总结，用中文输出深度分析报告（每篇≥300字：正文+评论+点评）。输出到对话并可选保存文件。
category: research
---

# Yahoo!ニュース 热榜爬取与分析

## 触发条件
- 用户提到「Yahoo日本热榜」「雅虎新闻」「yahoo jp」「ヤフーニュース」等
- 用户要求爬取日本新闻评论分析

## 前置条件
- 需要 browser 工具访问 JS 渲染页面
- 需要 terminal/curl 批量抓取静态 HTML

## 工作流

### 阶段 1：获取热榜列表
1. `browser_navigate` → https://news.yahoo.co.jp/topics/top-picks
2. `browser_console` 执行 JS 提取 pickup IDs：
```js
const links = document.querySelectorAll('a[href*="/pickup/"]');
const pickups = Array.from(links).map(l => {
  const m = l.href.match(/pickup/(\d+)/);
  return m ? {id: m[1], title: l.textContent.trim().substring(0, 120)} : null;
}).filter(Boolean);
// 去重取前25
JSON.stringify([...new Map(pickups.map(p => [p.id, p])).values()].slice(0, 25));
```

### 阶段 2：批量提取文章元数据
使用 `execute_code` + `terminal(curl)` 批量获取所有 pickup 页面：
```python
for pid in pickup_ids:
    r = terminal(f'curl -s -L -H "User-Agent: Mozilla/5.0" "https://news.yahoo.co.jp/pickup/{pid}"', timeout=10)
    # 提取: 主文章 ID (正则 /articles/([a-f0-9]+)/comments)
    # 提取: meta description
    # 提取: 来源媒体名
```

### 阶段 3：获取评论 AI 摘要（仅对有评论的文章）
使用 `delegate_task`（toolsets: ["browser"]）并行获取：
- 导航到 `https://news.yahoo.co.jp/articles/{article_id}/comments`
- 提取「ヤフコメAI要約」部分：
  - フォーカストピック：「〇〇」に注目
  - 主なヤフコメ（要点列表）
  - 関連ワード
  - コメント数
- 每批 3 个子代理，处理 3-5 篇文章

### 阶段 4：输出中文分析报告
格式要求：
```
### #N 标题
📝 正文: [文章内容中文总结，100-150字]
💬 评论区（N件）: [评论观点总结 + AI摘要引用]
🔍 点评: [个人深度分析，120-150字]
```
每篇总字数 ≥300 字。覆盖全部25篇。

### 已知问题
1. **部分 article 页面 404** — Yahoo 某些 topic 没有独立文章页，仅聚合页面存在
2. **评论数 JS 渲染** — curl 静态 HTML 中不含评论数，需 browser 或从 pickup 页面提取
3. **评论可能关闭** — 敏感政治/社会话题常被关闭评论
4. **同一事件多篇文章** — 不同媒体源报道同一事件会被列为独立 topic，需去重识别

## 输出目标
- 主输出：Telegram/Discord 对话中直接发送 Markdown 格式报告
- 可选保存：`~/.hermes/yahoo-reports/YYYY-MM-DD.md`
