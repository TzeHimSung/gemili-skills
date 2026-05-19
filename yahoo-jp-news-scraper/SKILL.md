---
name: yahoo-jp-news-scraper
description: Scrape Yahoo Japan News hot topics (Yahoo!ニュース トピックス一覧) — extract article summaries and AI-generated comment digests (ヤフコメAI要約). Handles pickup pages, /articles/ pages, and comments pages with dual curl+browser approach.
category: research
---

# Yahoo Japan News Hot Topics Scraper

Scrape and summarize Yahoo Japan News (news.yahoo.co.jp) hot topic listings, including article content and comment section AI summaries.

## Page Types

1. **Hot topic listing**: `https://news.yahoo.co.jp/topics/top-picks` — paginated list of 25 articles per page
2. **Pickup page**: `https://news.yahoo.co.jp/pickup/{id}` — topic hub aggregating multiple news sources with article snippet + comment preview
3. **Article page**: `https://news.yahoo.co.jp/articles/{article_id}` — full article (may 404 for aggregated topics)
4. **Comments page**: `https://news.yahoo.co.jp/articles/{article_id}/comments` — contains **ヤフコメAI要約** (AI comment summary) + full comments

## Key Findings

### Yahoo AI Comment Summary (ヤフコメAI要約)
Yahoo Japan provides an AI-generated summary of comment trends, including:
- **Focus topic** (「〇〇」に注目) — what the comments center on
- **Main opinions** (主なヤフコメは？) — 2 bullet points summarizing dominant views
- **Related keywords** (関連ワードは？) — 3 keywords

This is available either from Yahoo's preloaded/static payloads or browser-rendered UI depending on page shape; prefer curl/API first, then browser fallback.

### Article ID Extraction
- Pickup page HTML contains `/articles/{id}/comments` links — extract the one from the comment button, NOT just any /articles/ link (many are from ranking/related sections)
- Use regex: `/articles/([a-f0-9]+)/comments` on the pickup page curl output
- Some article IDs extracted this way return **404** — the article may have been deleted or is an aggregation-only topic without a standalone article page

### Comment Count
- top-picks static HTML currently includes `commentCount`; parse it via curl when present
- Pickup/comment pages may still render some counts dynamically; use browser fallback only when curl/preloaded payloads fail

### Browser Requirements
- Use `User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36` for curl
- Browser sessions work; stealth mode may trigger but usually succeeds
- Some articles may cause `ERR_NETWORK_CHANGED` — retry is usually sufficient

## Workflow

### Phase 1: Bulk Metadata via curl (fast)
```bash
# For each pickup_id, fetch the pickup page
curl -s -L -H "User-Agent: Mozilla/5.0..." "https://news.yahoo.co.jp/pickup/{id}"

# Extract:
# - Title: from <meta property="og:title"> or <h1>
# - Description: from <meta name="description">
# - Article ID: regex /articles/([a-f0-9]+)/comments (first match)
# - Comments URL: https://news.yahoo.co.jp/articles/{article_id}/comments
```

### Phase 2: AI Comment Summaries via Browser (parallel)
Use `delegate_task` with `toolsets: ["browser"]` to parallel-process comment pages (max 3 concurrent). AI summary extraction failures must be retried/rechecked in the same run; do not leave a placeholder such as “AI要約取得失敗” without a concrete `failure_reason`.

For each article:
1. `browser_navigate` to the comments URL
2. `browser_scroll` down to reveal the AI summary section
3. `browser_snapshot` to capture structured data
4. Extract: comment count, focus topic, opinions, keywords

If `/comments` returns 404, try the base `/articles/{id}` URL. If both 404, mark as unavailable with the URLs attempted and the reason.

Retry contract for browser/delegate fallback:
1. First try static/preloaded payloads from curl.
2. If missing, open the comments page in browser, scroll to the AI summary, and snapshot.
3. If browser output is empty, stale, or contains a network error (`ERR_NETWORK_CHANGED`, timeout, bot/challenge page), retry in the same run up to 3 total attempts: fresh `browser_navigate`, wait for stability, search/click likely expanders such as `もっと見る` / `AI要約` / `コメントをもっと見る`, then resnapshot.
4. If snapshots still do not expose the summary, use `browser_console(expression='document.body.innerText')` as the fallback visible-text channel.
5. If one worker returns `null` for a non-sports article that has a comments URL, dispatch one additional delegate/browser recheck for that article URL before finalizing failure.
6. Return structured JSON including `ai_summary`, `article_body`, `retry_count`, and `failure_reason`; downstream roast reports must either use a real summary or visibly explain the verified failure.

### Phase 3: Compile Report
Organize articles by category (sports, society, international, entertainment, science) based on title keywords. Include:
- Article summary (from description)
- Comment count
- AI summary (focus topic, opinions, keywords) when available

## Pitfalls

- **Article ID 404s**: Some pickup pages aggregate multiple news sources and don't have a standalone /articles/ page. The pickup page itself is the best source for those.
- **Comment count in curl**: top-picks static HTML currently exposes `commentCount`; validate page shape and fall back to browser only if curl/preloaded payloads fail.
- **Network errors**: `ERR_NETWORK_CHANGED` can occur; retry with a fresh browser_navigate and resnapshot before declaring summary unavailable.
- **No silent placeholders**: when used by `yahoo-jp-roast`, a failed AI summary extraction must be retried/reviewed in the same turn; do not output a bare placeholder as if it were content.
- **Duplicate topics**: Multiple pickup pages may reference the same article ID (e.g., multiple marathon articles share one ID).
- **Comments disabled**: Some articles (crime, sensitive topics) may have comments disabled entirely.

## Output Format

Present results as a categorized markdown report:
```
# 📊 Yahoo!ニュース 熱榜分析レポート
## Category (N articles)
### #N Title 💬N件
Content summary...
> 🤖 AI summary — Focus topic
> - Opinion 1
> - Opinion 2
> 🔑 keyword1 / keyword2 / keyword3
```
