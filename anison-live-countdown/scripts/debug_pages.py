#!/usr/bin/env python3
"""Debug: check raw pages for Liella!/虹ヶ咲/Aqours/μ's"""
import sys, re
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
from common import http_get, strip_html

PAGES = [
    ("Liella!", "https://www.lovelive-anime.jp/yuigaoka/news/", "https://www.lovelive-anime.jp/yuigaoka/"),
    ("虹ヶ咲", "https://www.lovelive-anime.jp/nijigasaki/live-event/", "https://www.lovelive-anime.jp/nijigasaki/"),
    ("Aqours", "https://www.lovelive-anime.jp/uranohoshi/news/", "https://www.lovelive-anime.jp/uranohoshi/"),
    ("μ's", "https://www.lovelive-anime.jp/news/", "https://www.lovelive-anime.jp/"),
]

for name, url, ref in PAGES:
    try:
        resp = http_get(url, referer=ref)
        html = resp.text
        # Count live-related keywords
        keywords = {
            'ライブ': 0, 'LIVE': 0, 'live': 0, '公演': 0, 'ツアー': 0,
            'tour': 0, 'event': 0, 'Event': 0,
        }
        for kw in keywords:
            keywords[kw] = html.count(kw)
        
        # Find dates
        dates = re.findall(r'\d{4}[年/.\-]\d{1,2}[月/.\-]\d{1,2}日?', html)
        
        # Find article/link blocks
        links = re.findall(r'href="([^"]*live[^"]*)"', html, re.IGNORECASE)
        
        print(f"\n{'='*60}")
        print(f"{name}: {url}")
        print(f"  Status: {resp.status_code}, Size: {len(html)} chars")
        print(f"  Keyword hits: {keywords}")
        print(f"  Dates found: {len(dates)}")
        for d in dates[:10]:
            print(f"    {d}")
        print(f"  Live links: {len(links)}")
        for l in links[:5]:
            print(f"    {l}")
        
        # Extract some content snippets
        text = strip_html(html)
        # Find lines with dates
        date_lines = [l.strip() for l in text.split('\n') if re.search(r'\d{4}[年/.\-]\d{1,2}[月/.\-]\d{1,2}', l)]
        print(f"  Lines with dates: {len(date_lines)}")
        for dl in date_lines[:10]:
            print(f"    {dl[:150]}")
            
    except Exception as e:
        print(f"\n{name}: ERROR - {e}")

print("\n\n=== eplus idolmaster check ===")
try:
    resp = http_get("https://eplus.jp/sf/word/0000031068")
    html = resp.text
    print(f"eplus 0000031068: status={resp.status_code}, size={len(html)}")
    ld = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
    print(f"JSON-LD blocks: {len(ld)}")
    for i, block in enumerate(ld):
        print(f"  Block {i}: {block[:200]}")
except Exception as e:
    print(f"eplus ERROR: {e}")
