#!/usr/bin/env python3
"""Deep check of Aqours and Liella! live page HTML structures"""
import sys, re
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
from common import http_get

# Liella! live/ 
resp = http_get("https://www.lovelive-anime.jp/yuigaoka/live/", referer="https://www.lovelive-anime.jp/yuigaoka/")
html = resp.text

# Find all <li> blocks that have live_title class
li_blocks = re.findall(r'<li>(.*?)</li>', html, re.DOTALL)
print("=== Liella! live/ ===")
print(f"Total <li> blocks: {len(li_blocks)}")
live_li = [li for li in li_blocks if 'live_title' in li]
print(f"<li> with live_title: {len(live_li)}")
for i, li in enumerate(live_li[:3]):
    # Extract title
    title_m = re.search(r'class="live_title"[^>]*>\s*<p>(.*?)</p>', li, re.DOTALL)
    title = re.sub(r'<[^>]+>', '', title_m.group(1)) if title_m else "?"
    # Extract date/schedule
    sched_m = re.search(r'class="live_info\s+schedule"[^>]*>(.*?)</div>', li, re.DOTALL)
    sched = re.sub(r'<[^>]+>', '', sched_m.group(1)).strip() if sched_m else "?"
    # Extract link
    link_m = re.search(r'href="([^"]+)"', li)
    link = link_m.group(1) if link_m else "?"
    # Extract venue
    venue_m = re.search(r'class="live_info\s+place"[^>]*>(.*?)</div>', li, re.DOTALL)
    venue = re.sub(r'<[^>]+>', '', venue_m.group(1)).strip() if venue_m else "?"
    print(f"\n  Live[{i}]:")
    print(f"    Title: {title[:80]}")
    print(f"    Schedule: {sched[:100]}")
    print(f"    Venue: {venue[:80]}")
    print(f"    Link: {link}")

# Check for any div with schedule class
sched_divs = re.findall(r'<div[^>]*class="[^"]*schedule[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
print(f"\nAll schedule divs: {len(sched_divs)}")
for i, sd in enumerate(sched_divs[:5]):
    clean = re.sub(r'<[^>]+>', '', sd).strip()[:150]
    print(f"  [{i}]: {clean}")

# Aqours live/
print("\n\n=== Aqours live/ ===")
resp2 = http_get("https://www.lovelive-anime.jp/uranohoshi/live/", referer="https://www.lovelive-anime.jp/uranohoshi/")
html2 = resp2.text

# Find schedule divs
sched_divs2 = re.findall(r'<div[^>]*class="[^"]*schedule[^"]*"[^>]*>(.*?)</div>', html2, re.DOTALL)
print(f"Schedule divs: {len(sched_divs2)}")
for i, sd in enumerate(sched_divs2[:5]):
    clean = re.sub(r'<[^>]+>', '', sd).strip()[:150]
    print(f"  [{i}]: {clean}")

# Find all li blocks with schedule content
li_all = re.findall(r'<li>(.*?)</li>', html2, re.DOTALL)
print(f"\nTotal <li> blocks: {len(li_all)}")
for i, li in enumerate(li_all):
    if 'schedule' in li:
        # extract title
        title_m = re.search(r'<h[3-5][^>]*>(.*?)</h[3-5]>', li, re.DOTALL)
        if not title_m:
            title_m = re.search(r'<p[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</p>', li, re.DOTALL)
        if not title_m:
            title_m = re.search(r'alt="([^"]*)"', li)
        title = re.sub(r'<[^>]+>', '', title_m.group(1))[:80] if title_m else "?"
        sched_m = re.search(r'class="[^"]*schedule[^"]*"[^>]*>(.*?)</div>', li, re.DOTALL)
        sched = re.sub(r'<[^>]+>', '', sched_m.group(1)).strip()[:100] if sched_m else "?"
        link_m = re.search(r'href="([^"]+)"', li)
        link = link_m.group(1) if link_m else "?"
        print(f"\n  Live[{i}]: title={title}, sched={sched[:80]}, link={link}")
