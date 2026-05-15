#!/usr/bin/env python3
"""
Yahoo JP Roast - 完整爬取管道
用法: python3 yahoo_jp_roast.py [--pages 3] [--top 20] [--archive-dir ~/.hermes/yahoo-reports]
输出: 筛体育→按评论降序→分类→带 Yahoo pickup + 原文链接的完整排名表
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import yahoo_rules  # noqa: E402

TOP_PICKS_URL = "https://news.yahoo.co.jp/topics/top-picks"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0 Safari/537.36"

SPORTS_KW = list(yahoo_rules.SPORTS_KEYWORDS)
SPORTS_ALLOWLIST = list(yahoo_rules.SPORTS_ALLOWLIST)

CATEGORIES = {
    "🌍国際政治": [
        "米", "トランプ", "アメリカ", "ワシントン", "マリ", "国防相", "軍民両用",
        "日米", "原油", "ホルムズ", "イラン", "中国", "日産", "自民", "滋賀",
        "高市", "首相", "米大統領", "銃撃", "発砲", "デモ", "排外", "外国人",
        "政治的暴力", "世論分断", "大阪", "アフリカ", "CNN", "夕食会", "大統領",
    ],
    "🎬エンタメ": [
        "MEGUMI", "東方神起", "内村", "24時間", "孤独のグルメ", "食堂",
        "三山凌輝", "秋元", "アイドル", "中丸", "アニメ", "芸能界",
        "松山千春", "有吉弘行", "松本人志", "櫻井", "嵐", "歌手", "橋本マナミ", "篠田麻里子",
    ],
    "🔬科学自然": ["蜃気楼", "地震", "気温", "GW期間", "山林火災", "気温変化"],
}
CATEGORY_ORDER = ["🌍国際政治", "🏥国内社会", "🎬エンタメ", "🔬科学自然"]


def _decode_json_string(raw: str) -> str:
    """Decode JSON escaped string fragments captured by regex."""
    try:
        return json.loads(f'"{raw}"')
    except json.JSONDecodeError:
        return raw.replace("\\u0026", "&").replace("\\/", "/")


def _fetch_page(page: int, tmp_dir: Path) -> tuple[Path, str]:
    url = TOP_PICKS_URL if page == 1 else f"{TOP_PICKS_URL}?page={page}"
    out = tmp_dir / f"yahoo_p{page}.html"
    result = subprocess.run(
        [
            "curl", "--fail", "--show-error", "--silent", "--location", "--compressed",
            "-H", f"User-Agent: {UA}", url,
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl failed for page {page}: {result.stderr.strip() or result.returncode}")
    html = result.stdout
    if '"commentCount"' not in html or '"id"' not in html:
        raise RuntimeError(f"Yahoo page shape changed or empty response: page {page}")
    out.write_text(html, encoding="utf-8")
    return out, html


def _extract_articles(html: str, page: int, seen: set[str]) -> dict[str, dict]:
    articles: dict[str, dict] = {}
    id_positions = [(m.start(), m.group(1)) for m in re.finditer(r'"id":(\d+)', html)]
    cc_positions = [(m.start(), int(m.group(1))) for m in re.finditer(r'"commentCount":(\d+)', html)]

    for id_pos, pid in id_positions:
        if pid in seen:
            continue
        match = next(((pos, val) for pos, val in cc_positions if pos > id_pos), None)
        if match is None:
            continue
        cc_pos, cc = match

        between = html[id_pos:cc_pos]
        title_matches = list(re.finditer(r'"title":"((?:[^"\\]|\\.)*)"', between))
        if not title_matches:
            continue
        title = _decode_json_string(title_matches[-1].group(1))

        after_cc = html[cc_pos:cc_pos + 3000]
        aurl_m = re.search(r'"articleUrl":"((?:[^"\\]|\\.)*)"', after_cc)
        aurl = _decode_json_string(aurl_m.group(1)) if aurl_m else ""

        seen.add(pid)
        articles[pid] = {
            "pid": pid,
            "title": title,
            "cc": cc,
            "aurl": aurl,
            "page": page,
            "purl": f"https://news.yahoo.co.jp/pickup/{pid}",
        }
    return articles


def _is_sports(title: str) -> bool:
    return yahoo_rules.is_sports(title)


def _category(title: str) -> str:
    for cat_name, keywords in CATEGORIES.items():
        if any(kw in title for kw in keywords):
            return cat_name
    return "🏥国内社会"


def build_report(pages: int, top: int | None, include_sports: bool, tmp_dir: Path) -> str:
    all_articles: dict[str, dict] = {}
    seen: set[str] = set()
    for page in range(1, pages + 1):
        _, html = _fetch_page(page, tmp_dir)
        all_articles.update(_extract_articles(html, page, seen))

    articles = list(all_articles.values())
    if not include_sports:
        articles = [a for a in articles if not _is_sports(a["title"])]
    articles.sort(key=lambda x: x["cc"], reverse=True)
    if top is not None:
        min_items = 20 if not include_sports else 0
        articles = articles[:max(top, min_items)]

    for article in articles:
        article["cat"] = _category(article["title"])

    lines = ["# Yahoo JP 热榜锐评", ""]
    for cat_name in CATEGORY_ORDER:
        items = [a for a in articles if a["cat"] == cat_name]
        if not items:
            continue
        lines.extend([f"## {cat_name} ({len(items)}篇)", ""])
        for item in items:
            lines.append(f'- [{item["cc"]}💬]({item["purl"]}) {item["title"]}')
            if item["aurl"]:
                lines.append(f'  原文: {item["aurl"]}')
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Yahoo JP top-picks 热榜筛选报表")
    parser.add_argument("--pages", type=int, default=3, help="抓取页数（默认 3）")
    parser.add_argument("--top", type=int, default=0, help="只保留评论数前 N 篇（默认全部）")
    parser.add_argument("--include-sports", action="store_true", help="调试用：不筛体育新闻")
    parser.add_argument("--archive-dir", default="~/.hermes/yahoo-reports", help="归档目录")
    parser.add_argument("--output", default="", help="额外写入指定文件；默认只写归档文件")
    parser.add_argument("--tmp-dir", default="/tmp", help="临时 HTML 保存目录")
    args = parser.parse_args()

    if args.pages < 1:
        raise SystemExit("--pages must be >= 1")
    top = args.top if args.top > 0 else None
    tmp_dir = Path(args.tmp_dir).expanduser()
    tmp_dir.mkdir(parents=True, exist_ok=True)

    report = build_report(args.pages, top, args.include_sports, tmp_dir)

    archive_dir = Path(args.archive_dir).expanduser()
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"{datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y-%m-%d')}-roast.md"
    archive_path.write_text(report, encoding="utf-8")

    if args.output:
        Path(args.output).expanduser().write_text(report, encoding="utf-8")

    print(report, end="")
    print(f"\n<!-- archived: {archive_path} -->", file=sys.stderr)


if __name__ == "__main__":
    main()
