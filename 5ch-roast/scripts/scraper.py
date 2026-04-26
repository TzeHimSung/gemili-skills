#!/usr/bin/env python3
"""
5ch-roast scraper
抓取 ikioig 前N条热帖及其评论，输出 JSON
"""
import re
import json
import html
import time
import subprocess
from datetime import datetime, timezone, timedelta

import os

JST = timezone(timedelta(hours=9))
N_THREADS = 100
DATE_DIR = datetime.now(JST).strftime('%Y-%m-%d')
OUTPUT_DIR = f'/mnt/d/hermes/5ch-reports/{DATE_DIR}'
OUTPUT = os.path.join(OUTPUT_DIR, 'raw_data.json')

def fetch(url, encoding='utf-8', retries=2):
    """curl 抓取 + 解码，支持重试"""
    for attempt in range(retries + 1):
        try:
            cmd = ['curl', '-sL', '-A',
                   'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                   '--max-time', '20', url]
            result = subprocess.run(cmd, capture_output=True, timeout=25)
            raw = result.stdout
            if not raw and attempt < retries:
                time.sleep(1)
                continue
            if encoding == 'shift-jis':
                for codec in ['shift-jis', 'cp932', 'utf-8', 'latin-1']:
                    try:
                        return raw.decode(codec, errors='replace')
                    except:
                        continue
            return raw.decode(encoding, errors='replace')
        except Exception as e:
            if attempt < retries:
                time.sleep(1)
            else:
                raise

def strip_html(text):
    text = re.sub(r'<[^>]*>', '', text)
    text = html.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()

def get_hot_threads(n=N_THREADS):
    """从 ikioig 获取热帖列表"""
    html = fetch('https://headline.5ch.io/ikioig/')
    cards = re.findall(r'<div class="card">(.*?)</div>\s*</div>', html, re.DOTALL)
    threads = []
    for card in cards:
        tag_m = re.search(r'<span class="tag">([^<]+)</span>', card)
        link_m = re.search(r'<a href="(https://[^"]+)"[^>]*>([^<]+)</a>', card)
        if not link_m:
            continue
        threads.append({
            'board': tag_m.group(1) if tag_m else '',
            'title': strip_html(link_m.group(2)),
            'url': link_m.group(1),
            'time': (re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', card) or [''])[0]
        })
    return threads[:n]

def _is_low_quality(text: str) -> bool:
    """过滤低质量评论。仅过滤过短评论，不再做内容过滤。

    注意：旧版声称「前39楼チョン/パヨ灌水乱码」经 2026-04-26 验证不属实。
    89条帖子 2139条评论中零条匹配旧乱码模式。5ch.io 评论内容正常，
    チョン/パヨ 是嫌儲等板块的真实讨论内容，不应过滤。
    """
    return len(text) < 2

def get_comments(thread_url):
    html = fetch(thread_url, encoding='shift-jis')
    posts = re.findall(
        r'<div id="\d+".*?class="clear post">(.*?)</div>\s*</div>',
        html, re.DOTALL)
    comments = []
    for p in posts:
        header_m = re.search(r'<div[^>]*class="post-header"[^>]*>(.*?)</div>', p, re.DOTALL)
        content_m = re.search(r'<div[^>]*class="post-content"[^>]*>(.*?)$', p, re.DOTALL)
        header_t = strip_html(header_m.group(1)) if header_m else ''
        content_t = strip_html(content_m.group(1)) if content_m else ''
        num_m = re.search(r'<span class="postid">(\d+)</span>', p)
        date_m = re.search(r'(\d{4}/\d{2}/\d{2}\([^)]+\)\s+\d{2}:\d{2}:\d{2}\.\d{2})', header_t)
        uid_m = re.search(r'ID:(\S+)', header_t)
        if _is_low_quality(content_t):
            continue
        comments.append({
            'num': int(num_m.group(1)) if num_m else 0,
            'date': date_m.group(1) if date_m else '',
            'uid': uid_m.group(1) if uid_m else '',
            'text': content_t[:500]
        })
    return comments[:30]  # 每条帖子最多取30条评论（供筛选用）

def main():
    print(f"🔍 5ch-roast: 抓取前{N_THREADS}条热帖...")
    threads = get_hot_threads(N_THREADS)
    results = []
    for i, t in enumerate(threads):
        print(f"  [{i+1}/{len(threads)}] {t['title'][:50]}...", end=' ')
        try:
            t['comments'] = get_comments(t['url'])
            t['comment_count'] = len(t['comments'])
            print(f"{t['comment_count']}评")
        except Exception as e:
            print(f"失败: {e}")
            t['comments'], t['comment_count'] = [], 0
        results.append(t)
        time.sleep(0.5)

    output = {
        'scrape_time': datetime.now(JST).isoformat(),
        'total': len(results),
        'threads': results
    }
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 保存: {OUTPUT} ({len(results)}帖)")

if __name__ == '__main__':
    main()
