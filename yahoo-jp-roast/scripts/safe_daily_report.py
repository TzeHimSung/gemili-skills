#!/usr/bin/env python3
"""Safe deterministic Yahoo JP daily report.

This script is designed for cron no_agent delivery: it prints only the final
user-facing Markdown report, with no tool-call JSON, scratchpad, or raw code.
"""
from __future__ import annotations

import html
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import yahoo_jp_roast as base  # noqa: E402

SPORTS_EXTRA = [
    "野球", "球団", "球場", "投手", "打者", "本塁打", "ホームラン", "被弾", "死球",
    "ドジャース", "ホワイトソックス", "大谷", "山本由伸", "由伸", "佐々木朗希", "朗希",
    "巨人", "西武", "DeNA", "SB戦", "ソフトバンク",
    "ラグビー", "バレー", "バレーボール", "バスケ", "Rマドリード", "守田英正",
    "フィギュア", "坂本花織", "始球式", "サイン盗み", "降格処分",
]
SPORTS_KEYWORDS = tuple(dict.fromkeys([*base.SPORTS_KW, *SPORTS_EXTRA]))

UA = base.UA


def fetch_url(url: str, timeout: int = 15) -> str:
    result = subprocess.run(
        [
            "curl", "--fail", "--show-error", "--silent", "--location", "--compressed",
            "-H", f"User-Agent: {UA}", url,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def extract_meta_description(page_html: str) -> str:
    if not page_html:
        return ""
    patterns = [
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
    ]
    for pattern in patterns:
        m = re.search(pattern, page_html, flags=re.I | re.S)
        if m:
            text = html.unescape(m.group(1))
            return re.sub(r"\s+", " ", text).strip()
    return ""


def comment_url(article_url: str) -> str:
    if "/articles/" in article_url and not article_url.endswith("/comments"):
        return article_url.rstrip("/") + "/comments"
    return ""


def is_sports(title: str) -> bool:
    return any(kw in title for kw in SPORTS_KEYWORDS) and not any(kw in title for kw in base.SPORTS_ALLOWLIST)


def dedupe_by_article(items: list[dict]) -> list[dict]:
    by_key: dict[str, dict] = {}
    for item in items:
        key = item.get("aurl") or item.get("purl") or item["pid"]
        # Strip query to merge duplicate pickup pages pointing at the same article.
        parsed = urlparse(key)
        norm_key = parsed._replace(query="", fragment="").geturl() if parsed.scheme else key
        existing = by_key.get(norm_key)
        if existing is None or item["cc"] > existing["cc"]:
            new_item = dict(item)
            new_item["pickup_urls"] = [item["purl"]]
            by_key[norm_key] = new_item
        else:
            existing.setdefault("pickup_urls", []).append(item["purl"])
    return sorted(by_key.values(), key=lambda x: x["cc"], reverse=True)


def collect_articles(pages: int, tmp_dir: Path) -> list[dict]:
    all_articles: dict[str, dict] = {}
    seen: set[str] = set()
    for page in range(1, pages + 1):
        _, page_html = base._fetch_page(page, tmp_dir)
        all_articles.update(base._extract_articles(page_html, page, seen))
    items = [a for a in all_articles.values() if not is_sports(a["title"])]
    items = dedupe_by_article(items)
    for item in items:
        item["cat"] = base._category(item["title"])
    return items


def ensure_min_articles(initial_pages: int, top: int, tmp_dir: Path, max_pages: int) -> list[dict]:
    """Fetch enough Yahoo top-picks pages to satisfy the no-agent report contract."""

    if initial_pages < 1:
        raise ValueError("initial_pages must be >= 1")
    if max_pages < initial_pages:
        raise ValueError("max_pages must be >= initial_pages")

    all_articles: dict[str, dict] = {}
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        _, page_html = base._fetch_page(page, tmp_dir)
        all_articles.update(base._extract_articles(page_html, page, seen))
        items = dedupe_by_article([a for a in all_articles.values() if not is_sports(a["title"])])
        if page >= initial_pages and len(items) >= top:
            for item in items:
                item["cat"] = base._category(item["title"])
            return items

    items = dedupe_by_article([a for a in all_articles.values() if not is_sports(a["title"])])
    for item in items:
        item["cat"] = base._category(item["title"])
    return items


def zh_comment_angle(item: dict) -> str:
    cc = item["cc"]
    title = item["title"]
    if cc >= 1000:
        heat = "评论区已经烧成小型公听会"
    elif cc >= 500:
        heat = "评论区热度不低，说明这事踩中了大众神经"
    elif cc >= 100:
        heat = "评论量中等，属于有人吵、但还没吵到全网失控"
    else:
        heat = "评论不多，更像是热榜上的观察样本"

    if any(k in title for k in ["物価", "倒産", "料金", "高騰", "補助", "日経平均", "不動産", "SBG"]):
        topic = "焦点大概率落在物价、补贴、资本市场和普通人实际体感之间的落差。"
    elif any(k in title for k in ["事故", "虐待", "逮捕", "死刑", "監禁", "強盗", "死亡", "重体"]):
        topic = "讨论核心通常会集中在责任链条、监管失灵和“为什么又是事后才发现”。"
    elif any(k in title for k in ["トランプ", "イラン", "米", "中国", "自民", "政府", "法案", "選挙"]):
        topic = "评论风向多半围绕政治算计、国家安全和政策到底是不是只会写作文。"
    elif any(k in title for k in ["CM", "芸", "俳優", "歌手", "松本人志", "細木", "舞台"]):
        topic = "吃瓜群众会在商业切割、公众形象和电视圈自我修复能力之间来回开火。"
    else:
        topic = "评论区大概率是一半讲现实焦虑，一半吐槽相关方反应太慢。"
    return f"{heat}；{topic}（注：本安全版不冒充已抓到ヤフコメAI要約。）"


def zh_roast(item: dict) -> str:
    title = item["title"]
    if any(k in title for k in ["物価", "料金", "高騰", "倒産", "補助"]):
        return "日本经济新闻最擅长把一个朴素问题包装成宏大叙事：钱包变薄是真的，会议变多也是真的。最后补贴像创可贴，贴上去很温柔，但伤口是谁划的，大家都装作没看见。"
    if any(k in title for k in ["事故", "虐待", "監禁", "強盗", "死亡", "重体"]):
        return "这类新闻最让人火大的地方，不是‘意外’两个字，而是每次事后都能翻出一串本该提前响的警报。制度像闹钟，平时静音，出事后音量拉满。"
    if any(k in title for k in ["自民", "政府", "法案", "選挙", "トランプ", "イラン", "中国", "米"]):
        return "政治新闻的固定剧本：先把问题拖成历史遗留，再把补救包装成英明决策。观众看久了也懂，真正稀缺的不是提案，而是有人愿意为结果负责。"
    if any(k in title for k in ["CM", "芸", "俳優", "歌手", "松本人志", "細木", "舞台", "アニメ"]):
        return "娱乐圈的风险管理越来越像便利店雨伞：晴天没人想起，下雨全员抢着买。品牌切割速度比事实核查还快，主打一个先保赞助商心率。"
    return "这条新闻的荒诞感在于，它看起来只是一个小事件，却能照出一整套社会运行逻辑：出事前靠惯性，出事后靠声明，最后靠网友帮忙把槽点整理成材料。"


def render_report(items: list[dict], top: int, archive_dir: Path | None = None) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    selected = items[:top]
    lines = [f"# Yahoo JP 热榜中文锐评日报（{now} JST）", ""]
    if len(selected) < top:
        raise ValueError(f"safe report requires at least {top} non-sports items; got {len(selected)}")

    for idx, item in enumerate(selected, 1):
        pickup_urls = item.get("pickup_urls") or [item["purl"]]
        desc = item.get("description", "")
        c_url = comment_url(item.get("aurl", ""))
        lines.append(f"## #{idx} {item['title']} — {item['cc']}💬")
        lines.append("原始链接：")
        for purl in pickup_urls[:3]:
            lines.append(f"- Pickup: {purl}")
        if item.get("aurl"):
            lines.append(f"- 原文: {item['aurl']}")
        if c_url:
            lines.append(f"- 评论: {c_url}")
        lines.append("")
        if desc:
            lines.append(f"📝 正文：Yahoo 摘要显示：{desc}")
        else:
            lines.append("📝 正文：已取得热榜标题和原始链接；原文摘要抓取为空，详细内容以原文为准。")
        lines.append(f"💬 评论：{zh_comment_angle(item)}")
        lines.append(f"🔍 锐评：{zh_roast(item)}")
        lines.append("")

    text = "\n".join(lines).rstrip() + "\n"
    if archive_dir:
        archive_dir.mkdir(parents=True, exist_ok=True)
        path = archive_dir / f"{datetime.now().strftime('%Y-%m-%d')}-roast-safe.md"
        path.write_text(text, encoding="utf-8")
    return text


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate safe deterministic Yahoo JP Chinese roast report")
    parser.add_argument("--pages", type=int, default=3)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--max-pages", type=int, default=8, help="auto-expand up to this many pages to satisfy --top")
    parser.add_argument("--tmp-dir", default="/tmp")
    parser.add_argument("--archive-dir", default="~/.hermes/yahoo-reports")
    args = parser.parse_args()

    tmp_dir = Path(args.tmp_dir).expanduser()
    tmp_dir.mkdir(parents=True, exist_ok=True)
    items = ensure_min_articles(args.pages, args.top, tmp_dir, args.max_pages)
    if len(items) < args.top:
        print(
            f"Yahoo JP safe report aborted: only {len(items)} non-sports items after {args.max_pages} page(s); required {args.top}",
            file=sys.stderr,
        )
        return 1

    # Fetch pickup meta descriptions only for the selected top items to keep cron fast.
    for item in items[: args.top]:
        page_html = fetch_url(item["purl"])
        item["description"] = extract_meta_description(page_html)

    report = render_report(items, args.top)

    forbidden = [
        "delegate_task", "default_api", "```python", "```json", "tool_calls",
        "browser_snapshot", "functions.", "I will", "The first step", "下一步我会",
    ]
    if any(marker in report for marker in forbidden):
        print("Yahoo JP safe report aborted: forbidden internal marker detected", file=sys.stderr)
        return 1

    archive_dir = Path(args.archive_dir).expanduser()
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"{datetime.now().strftime('%Y-%m-%d')}-roast-safe.md"
    archive_path.write_text(report, encoding="utf-8")
    print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
