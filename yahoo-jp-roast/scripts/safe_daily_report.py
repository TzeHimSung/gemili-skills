#!/usr/bin/env python3
"""Safe deterministic Yahoo JP daily report.

This script is designed for cron no_agent delivery: it prints only the final
user-facing Markdown report, with no tool-call JSON, scratchpad, or raw code.
"""
from __future__ import annotations

import hashlib
import html
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

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
JST = ZoneInfo("Asia/Tokyo")

FORBIDDEN_MARKERS = [
    "delegate_task", "default_api", "```python", "```json", "tool_calls",
    "browser_snapshot", "functions.", "I will", "The first step", "下一步我会",
]


def jst_now(now: datetime | None = None) -> datetime:
    """Return report/archive time normalized to Japan Standard Time."""
    if now is None:
        return datetime.now(JST)
    if now.tzinfo is None:
        return now.replace(tzinfo=JST)
    return now.astimezone(JST)


def jst_date_key(now: datetime | None = None) -> str:
    return jst_now(now).strftime("%Y-%m-%d")


def jst_now_label(now: datetime | None = None) -> str:
    return jst_now(now).strftime("%Y-%m-%d %H:%M")


def has_original_article_url(item: dict) -> bool:
    raw_url = item.get("aurl")
    if not isinstance(raw_url, str):
        return False
    url = raw_url.strip()
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.netloc == "news.yahoo.co.jp" and parsed.path.startswith("/articles/")


def original_article_url(item: dict) -> str:
    require_original_article_urls([item], 1)
    return item["aurl"].strip()


def require_original_article_urls(items: list[dict], top: int) -> None:
    missing = [
        str(item.get("pid") or item.get("purl") or idx)
        for idx, item in enumerate(items[:top], 1)
        if not has_original_article_url(item)
    ]
    if missing:
        raise ValueError(
            "safe report requires original article URL for every published item; "
            f"missing original article URL for: {', '.join(missing)}"
        )


def assert_no_forbidden_markers(texts: list[str]) -> None:
    for idx, text in enumerate(texts, 1):
        bad = [marker for marker in FORBIDDEN_MARKERS if marker in text]
        if bad:
            raise RuntimeError(f"message #{idx} contains forbidden internal marker(s): {bad}")


def assert_no_forbidden_item_fields(items: list[dict], top: int) -> None:
    texts: list[str] = []
    for item in items[:top]:
        for key in ("title", "purl", "aurl", "description"):
            value = item.get(key)
            if isinstance(value, str):
                texts.append(value)
        for pickup_url in item.get("pickup_urls") or []:
            if isinstance(pickup_url, str):
                texts.append(pickup_url)
    assert_no_forbidden_markers(texts)


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


def comment_url(article_url: str | None) -> str:
    if not isinstance(article_url, str):
        return ""
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
        if existing is None:
            new_item = dict(item)
            new_item["pickup_urls"] = [item["purl"]]
            by_key[norm_key] = new_item
        elif item["cc"] > existing["cc"]:
            pickup_urls = [*existing.get("pickup_urls", []), item["purl"]]
            new_item = dict(item)
            new_item["pickup_urls"] = pickup_urls
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
    items = [a for a in all_articles.values() if not is_sports(a["title"]) and has_original_article_url(a)]
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
        items = dedupe_by_article([a for a in all_articles.values() if not is_sports(a["title"]) and has_original_article_url(a)])
        if page >= initial_pages and len(items) >= top:
            for item in items:
                item["cat"] = base._category(item["title"])
            return items

    items = dedupe_by_article([a for a in all_articles.values() if not is_sports(a["title"]) and has_original_article_url(a)])
    for item in items:
        item["cat"] = base._category(item["title"])
    return items


def _stable_index(key: str, size: int) -> int:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % size


def _pick(options: list[str], key: str) -> str:
    return options[_stable_index(key, len(options))]


def _short(text: str, limit: int = 72) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _topic(title: str) -> str:
    if any(k in title for k in ["物価", "料金", "高騰", "値上", "倒産", "補助", "不動産", "赤字", "日経平均", "株", "SBG", "ホンダ", "カルビー", "カゴメ", "ENEOS", "ナフサ"]):
        return "economy"
    if any(k in title for k in ["事故", "虐待", "逮捕", "死刑", "監禁", "強盗", "死亡", "重体", "殺人", "殴", "救急", "不合格", "児童", "授業", "バス"]):
        return "society"
    if any(k in title for k in ["トランプ", "イラン", "米", "中国", "習", "自民", "政府", "法案", "選挙", "首相", "台湾", "ホルムズ", "プーチン"]):
        return "politics"
    if any(k in title for k in ["CM", "芸", "俳優", "歌手", "松本人志", "細木", "舞台", "アニメ", "アイドル", "ホワイトハウス"]):
        return "entertainment"
    return "general"


def zh_comment_angle(item: dict) -> str:
    cc = item["cc"]
    title = item["title"]
    key = f"comment:{item.get('pid')}:{title}"
    if cc >= 1000:
        heat = _pick([
            "评论区已经烧成小型公听会",
            "评论数破千，基本可以确定不是路人随手点进来",
            "热度够高，雅虎评论区又开始代替圆桌会议上班",
        ], key)
    elif cc >= 500:
        heat = _pick([
            "评论区热度不低，说明这事踩中了大众神经",
            "几百条评论堆起来，已经足够看出民意温度",
            "讨论量明显起势，属于会被办公室茶水间顺手拿来聊的新闻",
        ], key)
    elif cc >= 100:
        heat = _pick([
            "评论量中等，属于有人吵、但还没吵到全网失控",
            "声量不算爆炸，但足够暴露大家最在意的那个点",
            "讨论还在发酵阶段，情绪比数字本身更有看头",
        ], key)
    else:
        heat = _pick([
            "评论不多，更像是热榜上的观察样本",
            "声量偏小，但标题已经足够把问题摆上桌",
            "评论区还没炸锅，先当作舆情温度计读数偏低",
        ], key)

    topics = {
        "economy": [
            f"围绕《{title}》，焦点多半是成本上涨最终又由谁买单。",
            "读者大概率会把供应链、价格标签和工资单放在一起骂。",
            "经济叙事再宏大，评论区最后还是会落回钱包体感。",
        ],
        "society": [
            f"围绕《{title}》，讨论核心会集中在责任链条有没有提前断电。",
            "评论风向通常会追问：警报到底响过没有，为什么总是事后才算数。",
            "这类社会新闻最容易把愤怒引向监管、现场处置和迟来的解释。",
        ],
        "politics": [
            f"围绕《{title}》，评论区多半会拆政策姿态和现实利益之间的缝。",
            "政治话题的火药味会落在安全、外交筹码和谁在对国内观众表演。",
            "读者大概率不会只看声明，而会追问这场话术谁受益、谁埋单。",
        ],
        "entertainment": [
            f"围绕《{title}》，吃瓜群众会盯着商业切割和公众形象的速度差。",
            "娱乐/名人话题通常不是只看事实，还要看各方公关有没有露怯。",
            "评论区会在同情、嘲讽和‘早该想到’之间反复横跳。",
        ],
        "general": [
            f"围绕《{title}》，评论区大概率是一半讲现实焦虑，一半吐槽相关方反应太慢。",
            "看似小事件，评论区往往会把它扩写成一堂社会运行学公开课。",
            "大家争的未必是标题本身，而是标题背后那套熟悉得令人疲惫的逻辑。",
        ],
    }
    topic = _pick(topics[_topic(title)], key + ":topic")
    if title not in topic:
        topic = f"围绕《{title}》，{topic}"
    return f"{heat}；{topic}（注：本安全版不冒充已抓到ヤフコメAI要約。）"


def zh_roast(item: dict) -> str:
    title = item["title"]
    desc = _short(item.get("description", ""), 84)
    subject = f"《{title}》"
    if desc:
        lead = _pick([
            f"这条的关键信息是：{desc}",
            f"Yahoo 摘要已经把荒诞点递到嘴边：{desc}",
            f"光看摘要就够拧巴：{desc}",
        ], f"lead:{item.get('pid')}:{title}")
    else:
        lead = f"这条新闻没有抓到完整摘要，只能先按标题 {subject} 看热闹。"

    roasts = {
        "economy": [
            f"{lead} 经济新闻最会把生活压力翻译成漂亮名词：供应链、成本、汇率、战略调整，听起来都很专业，落到普通人手里就是又贵、又少、还得自己理解。",
            f"{lead} 企业和政策层的解释通常像说明书第17页的小字：每个字都没错，但消费者真正看到的只有价格牌。所谓市场波动，最后总能精准波动到老百姓的钱包上。",
            f"{lead} 这类新闻的魔幻之处在于，上游有上游的难处，下游有下游的苦衷，唯独中间那个买单的人没有发言席，只能在评论区申请精神赔偿。",
        ],
        "society": [
            f"{lead} 社会新闻最刺人的地方，是它总能在事后证明‘本来可以早点做点什么’。等通报出来，流程完整、措辞稳妥，但受害者已经替所有人的迟钝付过账。",
            f"{lead} 每次看到这种标题，都像在看制度的迟到打卡：平时安静如鸡，出事后文件、调查、说明一套一套赶来，效率突然像被雷劈醒。",
            f"{lead} 这里最该被吐槽的不是某一个细节，而是那条从现场到管理层的责任传送带：运行时没人看，坏了才发现保修卡早过期。",
        ],
        "politics": [
            f"{lead} 政治新闻的惯用手法是把选择题包装成原则题，再把代价藏进脚注里。台上讲大局，台下算账本，观众负责从措辞缝里找真实意图。",
            f"{lead} 外交和政策声明最像大型多人话术游戏：每方都说自己站在历史正确一边，至于现实成本谁承担，通常留给明天的新闻继续解释。",
            f"{lead} 这种议题的看点从来不只是说了什么，而是谁必须这样说、说给谁听。政治的高级感很多时候就是把尴尬讲得像战略。",
        ],
        "entertainment": [
            f"{lead} 娱乐圈和品牌公关最现实：风向一变，温情滤镜立刻下架，风险管理比剧情反转还快。观众还在等真相，赞助商已经先把心率稳住。",
            f"{lead} 名人新闻的标准流程越来越熟：先上热搜，再出声明，然后网友做阅读理解。真正辛苦的是评论区，既要当陪审团，还要兼职公关质检。",
            f"{lead} 这类瓜的核心不是八卦本身，而是每个人都在用最快速度确认自己会不会被连坐。娱乐工业的体面，往往脆得像一次性餐盒。",
        ],
        "general": [
            f"{lead} 荒诞感就在这里：一个看似局部的小事件，往往能照出一整套社会惯性。出事前靠默认设置，出事后靠正式声明，最后靠网友把槽点整理成教材。",
            f"{lead} 这新闻像一面便利店玻璃门，推开前以为只是日常，撞上去才发现上面写满了规则漏洞、沟通失灵和‘下次一定改’。",
            f"{lead} 它不一定是当天最大事件，却很适合当社会压力测试题：相关方反应快不快、解释真不真、公众还愿不愿意买账，一测全露馅。",
        ],
    }
    return _pick(roasts[_topic(title)], f"roast:{item.get('pid')}:{title}")


def render_report(items: list[dict], top: int, archive_dir: Path | None = None) -> str:
    now = jst_now_label()
    selected = items[:top]
    lines = [f"# Yahoo JP 热榜中文锐评日报（{now} JST）", ""]
    if len(selected) < top:
        raise ValueError(f"safe report requires at least {top} non-sports items with original article URL; got {len(selected)}")
    require_original_article_urls(selected, top)
    assert_no_forbidden_item_fields(selected, top)

    for idx, item in enumerate(selected, 1):
        pickup_urls = item.get("pickup_urls") or [item["purl"]]
        aurl = original_article_url(item)
        desc = item.get("description", "")
        c_url = comment_url(aurl)
        lines.append(f"## #{idx} {item['title']} — {item['cc']}💬")
        lines.append("原始链接：")
        for purl in pickup_urls[:3]:
            lines.append(f"- Pickup: {purl}")
        lines.append(f"- 原文: {aurl}")
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
    assert_no_forbidden_markers([text])
    if archive_dir:
        archive_dir.mkdir(parents=True, exist_ok=True)
        path = archive_dir / f"{jst_date_key()}-roast-safe.md"
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
            f"Yahoo JP safe report aborted: only {len(items)} non-sports item(s) with original article URL after {args.max_pages} page(s); required {args.top}",
            file=sys.stderr,
        )
        return 1

    try:
        require_original_article_urls(items, args.top)
        assert_no_forbidden_item_fields(items, args.top)
        # Fetch pickup meta descriptions only for the selected top items to keep cron fast.
        for item in items[: args.top]:
            page_html = fetch_url(item["purl"])
            item["description"] = extract_meta_description(page_html)
        report = render_report(items, args.top)
    except RuntimeError as exc:
        print(f"Yahoo JP safe report aborted: forbidden internal marker detected: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Yahoo JP safe report aborted: {exc}", file=sys.stderr)
        return 1

    archive_dir = Path(args.archive_dir).expanduser()
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"{jst_date_key()}-roast-safe.md"
    archive_path.write_text(report, encoding="utf-8")
    print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
