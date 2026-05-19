"""Legacy debug helper for inspecting cached Yahoo JP top-picks HTML.

This script is intentionally not part of the production no-agent pipeline.
Use ``safe_daily_report.py`` / ``send_safe_daily_items.py`` for cron delivery.
It only reads already-fetched local HTML files and prints a diagnostic summary.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from yahoo_rules import is_sports

DEBUG_ONLY = True


def extract_articles_from_html(html: str, page: int, seen: set[str] | None = None) -> dict[str, dict]:
    """Extract article candidates from one cached top-picks HTML page."""
    seen = seen if seen is not None else set()
    articles: dict[str, dict] = {}
    id_positions = [(m.start(), m.group(1)) for m in re.finditer(r'"id":(\d+)', html)]
    cc_positions = [(m.start(), int(m.group(1))) for m in re.finditer(r'"commentCount":(\d+)', html)]

    for id_pos, pid in id_positions:
        if pid in seen:
            continue
        cc = None
        cc_pos = None
        for cand_pos, cc_val in cc_positions:
            if cand_pos > id_pos:
                cc = cc_val
                cc_pos = cand_pos
                break
        if cc is None or cc_pos is None:
            continue

        between = html[id_pos:cc_pos]
        title_matches = list(re.finditer(r'"title":"((?:[^"\\]|\\.)*)"', between))
        if not title_matches:
            continue
        title = title_matches[-1].group(1)

        after_cc = html[cc_pos:cc_pos + 2000]
        aurl_m = re.search(r'"articleUrl":"((?:[^"\\]|\\.)*)"', after_cc)
        aurl = aurl_m.group(1).replace('\\u0026', '&') if aurl_m else ''

        seen.add(pid)
        articles[pid] = {
            'pid': pid,
            'title': title,
            'cc': cc,
            'aurl': aurl,
            'page': page,
            'purl': f'https://news.yahoo.co.jp/pickup/{pid}',
            'curl': f'{aurl}/comments' if aurl else '',
        }
    return articles


def categorize(title: str) -> str:
    intl = ['米', 'トランプ', 'アメリカ', 'ワシントン', '国防相', '日米', '原油', 'ホルムズ', 'イラン', '中国', '自民', '首相', 'デモ', '大統領']
    ent = ['MEGUMI', '東方神起', '内村', '孤独のグルメ', 'アイドル', 'アニメ', '芸能界', '嵐', '歌手']
    sci = ['蜃気楼', '地震', '気温', '山林火災']

    if any(kw in title for kw in intl):
        return '🌍国際政治'
    if any(kw in title for kw in ent):
        return '🎬エンタメ'
    if any(kw in title for kw in sci):
        return '🔬科学自然'
    return '🏥国内社会'


def load_cached_articles(paths: list[Path]) -> list[dict]:
    all_articles: dict[str, dict] = {}
    seen: set[str] = set()
    for page, path in enumerate(paths, 1):
        html = path.read_text(encoding='utf-8')
        all_articles.update(extract_articles_from_html(html, page, seen))

    non_sports = [a for a in all_articles.values() if not is_sports(a['title'])]
    non_sports.sort(key=lambda x: x['cc'], reverse=True)
    for article in non_sports:
        article['cat'] = categorize(article['title'])
    return non_sports


def render_summary(non_sports: list[dict], total_count: int) -> str:
    lines = [
        f'爬取: {total_count}篇 | 体育筛除: {total_count - len(non_sports)}篇 | 最终: {len(non_sports)}篇',
        '',
    ]
    cats: dict[str, list[dict]] = {}
    for article in non_sports:
        cats.setdefault(article['cat'], []).append(article)

    for cat_name in ['🌍国際政治', '🏥国内社会', '🎬エンタメ', '🔬科学自然']:
        items = sorted(cats.get(cat_name, []), key=lambda x: x['cc'], reverse=True)
        lines.append(f'\n## {cat_name} ({len(items)}篇)')
        for article in items:
            lines.append(f'{article["cc"]:5d}💬|{article["pid"]}|{article["title"][:60]}')
            lines.append(f'      pickup: {article["purl"]}')
            if article['aurl']:
                lines.append(f'      article: {article["aurl"]}')
    return '\n'.join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='DEBUG ONLY: inspect cached Yahoo JP top-picks HTML files')
    parser.add_argument('paths', nargs='*', type=Path, default=[Path(f'/tmp/yahoo_p{i}.html') for i in range(1, 4)])
    args = parser.parse_args(argv)

    missing = [str(path) for path in args.paths if not path.exists()]
    if missing:
        print('DEBUG ONLY: missing cached HTML files: ' + ', '.join(missing))
        return 1

    all_articles: dict[str, dict] = {}
    seen: set[str] = set()
    for page, path in enumerate(args.paths, 1):
        all_articles.update(extract_articles_from_html(path.read_text(encoding='utf-8'), page, seen))
    non_sports = [a for a in all_articles.values() if not is_sports(a['title'])]
    non_sports.sort(key=lambda x: x['cc'], reverse=True)
    for article in non_sports:
        article['cat'] = categorize(article['title'])
    print(render_summary(non_sports, len(all_articles)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
