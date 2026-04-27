#!/usr/bin/env python3
"""Debug: check HTML structure of Liella! and 虹ヶ咲 pages"""
import sys, re
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
from common import http_get

# Liella! - check article/link structure
resp = http_get("https://www.lovelive-anime.jp/yuigaoka/news/", referer="https://www.lovelive-anime.jp/yuigaoka/")
html = resp.text
print("=== Liella! HTML structure ===")
# Find <li> blocks
li_blocks = re.findall(r'<li[^>]*>(.*?)</li>', html, re.DOTALL)
print(f"<li> blocks: {len(li_blocks)}")
for i, li in enumerate(li_blocks[:3]):
    print(f"  li[{i}]: {li[:300]}")
    print("  ---")

# Find article blocks
art_blocks = re.findall(r'<article[^>]*>(.*?)</article>', html, re.DOTALL)
print(f"\n<article> blocks: {len(art_blocks)}")
for i, a in enumerate(art_blocks[:3]):
    print(f"  article[{i}]: {a[:400]}")
    print("  ---")

# Check for link structure
links = re.findall(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', html, re.DOTALL)
print(f"\nAll links: {len(links)}")
for href, text in links[:10]:
    clean = re.sub(r'<[^>]+>', '', text).strip()[:80]
    print(f"  {href} -> {clean}")

# Look for news/article list patterns
divs = re.findall(r'<div[^>]*class="([^"]*)"[^>]*>(.*?)</div>', html, re.DOTALL)
print(f"\nDiv classes: {len(divs)}")
for cls, content in divs:
    if any(kw in cls.lower() for kw in ['news', 'article', 'list', 'item', 'event']):
        print(f"  .{cls}: {content[:200]}")
        print("  ---")

print("\n\n=== 虹ヶ咲 live-event HTML structure ===")
resp2 = http_get("https://www.lovelive-anime.jp/nijigasaki/live-event/", referer="https://www.lovelive-anime.jp/nijigasaki/")
html2 = resp2.text

# Check for sections
sections = re.findall(r'<section[^>]*>(.*?)</section>', html2, re.DOTALL)
print(f"<section> blocks: {len(sections)}")
for i, s in enumerate(sections[:3]):
    print(f"  section[{i}]: {s[:300]}")
    print("  ---")

# Check for .live-event specific divs
divs2 = re.findall(r'<div[^>]*class="([^"]*)"[^>]*>(.*?)</div>', html2, re.DOTALL)
print(f"\nDiv classes: {len(divs2)}")
for cls, content in divs2:
    if any(kw in cls.lower() for kw in ['live', 'event', 'card', 'list', 'inner', 'item']):
        print(f"  .{cls}: {content[:200]}")
        print("  ---")

print("\n\n=== Check 虹ヶ咲 live.php ===")
resp3 = http_get("https://www.lovelive-anime.jp/nijigasaki/live/live.php", referer="https://www.lovelive-anime.jp/nijigasaki/")
html3 = resp3.text
print(f"live.php: status={resp3.status_code}, size={len(html3)}")
# Find dates
dates3 = re.findall(r'\d{4}[年/.\-]\d{1,2}[月/.\-]\d{1,2}日?', html3)
print(f"Dates: {len(dates3)}")
for d in dates3[:10]:
    print(f"  {d}")
