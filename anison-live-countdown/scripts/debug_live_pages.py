#!/usr/bin/env python3
"""Check HTML structure of Liella! live/ and Aqours live/"""
import sys, re
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
from common import http_get

pages = [
    ("Liella! live/", "https://www.lovelive-anime.jp/yuigaoka/live/", "https://www.lovelive-anime.jp/yuigaoka/"),
    ("Aqours live/", "https://www.lovelive-anime.jp/uranohoshi/live/", "https://www.lovelive-anime.jp/uranohoshi/"),
]

for name, url, ref in pages:
    resp = http_get(url, referer=ref)
    html = resp.text
    print(f"\n{'='*60}")
    print(f"{name}: size={len(html)}")
    
    # look for list-like structures
    for tag in ['ul', 'ol', 'table', 'section']:
        blocks = re.findall(f'<{tag}[^>]*>(.*?)</{tag}>', html, re.DOTALL)
        if blocks:
            # find ones with content
            content_blocks = [(i, b) for i, b in enumerate(blocks) if len(b.strip()) > 100]
            print(f"  <{tag}>: {len(blocks)} total, {len(content_blocks)} with content")
            for idx, b in content_blocks[:2]:
                print(f"    {tag}[{idx}]: {b[:400]}")
                print("    ---")
    
    # look for date patterns in HTML context
    # Search for "年" near "live" / "event" context
    date_matches = list(re.finditer(r'(202[6-9])[年/.\-](\d{1,2})[月/.\-](\d{1,2})日?', html))
    print(f"  Future dates: {len(date_matches)}")
    for m in date_matches[:5]:
        ctx_start = max(0, m.start()-100)
        ctx_end = min(len(html), m.end()+100)
        ctx = re.sub(r'<[^>]+>', ' ', html[ctx_start:ctx_end])
        ctx = re.sub(r'\s+', ' ', ctx).strip()
        print(f"    [{m.group()}] ...{ctx[:200]}...")
    
    # Check for stage/date format (like 蓮ノ空)
    stage_blocks = re.findall(r'＜([^／]+)／([^＞>\n]+)[＞>]?', html)
    print(f"  Stage/Date blocks: {len(stage_blocks)}")
    for s in stage_blocks[:5]:
        print(f"    {s}")
