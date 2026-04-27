#!/usr/bin/env python3
"""Debug: try alternate URLs for Liella!/虹ヶ咲/Aqours live pages"""
import sys, re
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
from common import http_get

URLS = [
    ("Liella! live/", "https://www.lovelive-anime.jp/yuigaoka/live/"),
    ("Liella! live/index", "https://www.lovelive-anime.jp/yuigaoka/live/index.php"),
    ("Liella! event news", "https://www.lovelive-anime.jp/yuigaoka/news/?cat=126"),
    ("虹ヶ咲 live_detail flower", "https://www.lovelive-anime.jp/nijigasaki/live/live_detail.php?p=flower_live"),
    ("虹ヶ咲 live_detail 8th", "https://www.lovelive-anime.jp/nijigasaki/live/live_detail.php?p=8thlive"),
    ("虹ヶ咲 live index", "https://www.lovelive-anime.jp/nijigasaki/live/index.php"),
    ("虹ヶ咲 live/", "https://www.lovelive-anime.jp/nijigasaki/live/"),
    ("Aqours live_detail jimoai", "https://www.lovelive-anime.jp/uranohoshi/live/live_detail.php?p=jimoai2025"),
    ("Aqours live_detail documentary", "https://www.lovelive-anime.jp/uranohoshi/live/live_detail.php?p=aqours_documentary"),
    ("Aqours live index", "https://www.lovelive-anime.jp/uranohoshi/live/index.php"),
    ("Aqours live/", "https://www.lovelive-anime.jp/uranohoshi/live/"),
    ("LoveLive Special live", "https://www.lovelive-anime.jp/special/live/live_detail.php?p=jimoai2025"),
]

for name, url in URLS:
    try:
        resp = http_get(url, referer="https://www.lovelive-anime.jp/")
        html = resp.text
        # Find dates with year >= 2026
        dates = re.findall(r'(202[6-9])[年/.\-](\d{1,2})[月/.\-](\d{1,2})日?', html)
        future_dates = [(y,m,d) for y,m,d in dates if int(y) >= 2026]
        # Count live keywords
        live_kw = html.lower().count('live') + html.count('ライブ') + html.count('公演')
        print(f"{name}: status={resp.status_code}, size={len(html)}, dates>2026={len(future_dates)}, live_kw={live_kw}")
        if future_dates:
            for y,m,d in future_dates[:5]:
                print(f"  {y}-{m}-{d}")
        # Extract titles
        titles = re.findall(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE)
        print(f"  title: {titles[0][:80] if titles else 'none'}")
    except Exception as e:
        print(f"{name}: ERROR - {type(e).__name__}: {e}")
