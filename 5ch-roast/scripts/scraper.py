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
BASE_DIR = os.environ.get('HERMES_5CH_REPORT_DIR', '/mnt/d/hermes/5ch-reports')
DATE_DIR = datetime.now(JST).strftime('%Y-%m-%d')
OUTPUT_DIR = os.path.join(BASE_DIR, DATE_DIR)
OUTPUT = os.path.join(OUTPUT_DIR, 'raw_data.json')

def _decode_score(text):
    """越小越好：惩罚替换符和典型 mojibake，帮助 Shift-JIS/UTF-8 自动回退。"""
    mojibake_markers = ['�', '縺', '繧', '譁', '荳', '蜿', '螟', '縲', 'ｽ']
    marker_penalty = sum(text.count(m) for m in mojibake_markers) * 10
    replacement_penalty = text.count('�') * 50
    control_penalty = sum(1 for ch in text if ord(ch) < 32 and ch not in '\r\n\t') * 5
    return replacement_penalty + marker_penalty + control_penalty


def _decode_bytes(raw, encoding='utf-8'):
    if encoding == 'shift-jis':
        codecs = ['shift-jis', 'cp932', 'utf-8', 'latin-1']
    else:
        codecs = [encoding, 'utf-8', 'cp932', 'latin-1']

    candidates = []
    for codec in dict.fromkeys(codecs):
        try:
            text = raw.decode(codec, errors='strict')
        except UnicodeError:
            text = raw.decode(codec, errors='replace')
        candidates.append((_decode_score(text), codec, text))
    candidates.sort(key=lambda item: item[0])
    return candidates[0][2]


def fetch(url, encoding='utf-8', retries=2):
    """curl 抓取 + 解码，支持重试。"""
    for attempt in range(retries + 1):
        try:
            cmd = ['curl', '-sL', '-A',
                   'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                   '--max-time', '20', url]
            result = subprocess.run(cmd, capture_output=True, timeout=25)
            raw = result.stdout
            if result.returncode != 0:
                if attempt < retries:
                    time.sleep(1)
                    continue
                stderr = _decode_bytes(result.stderr or b'', encoding)
                raise RuntimeError(f"curl failed for {url}: {stderr[:200]}")
            if not raw and attempt < retries:
                time.sleep(1)
                continue
            if not raw:
                raise RuntimeError(f"empty response from {url}")
            return _decode_bytes(raw, encoding)
        except Exception:
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
    """过滤低质量评论：过短 + bot 灌水。

    bot 灌水特征（2026-04-27 实数据验证）：
    含「チョン」或「パヨ」+ 无日语句法结构 + 长度 > 5。
    使用语法二元组检测（には、ている、した 等），
    防止单个假名（に、の、を）在随机序列中被误判为语法。

    保留：麻坂チョン 等 ≤5 字的真实缩写、
    含真正句法结构的正常讨论（如「監督チョンコ、失うモノ」）。
    """
    if len(text) < 2:
        return True

    # bot 灌水检测：含チョン/パヨ 但无语法结构
    if 'チョン' in text or 'パヨ' in text:
        if len(text) <= 5:
            return False
        # 检查是否有日语语法二元组（连续两个假名构成的语法模式）
        grammar_bigrams = [
            'には', 'では', 'のは', 'のが', 'かを', 'への', 'とは',
            'して', 'した', 'する', 'いる', 'ある', 'なる', 'くる',
            'です', 'ます', 'した', 'ない', 'かった', 'れば', 'ても',
            'から', 'まで', 'など', 'けど', 'ので', 'のに', 'なら',
            'よう', 'こと', 'もの', 'はず', 'べき', 'つつ', 'ながら',
            'たい', 'だろう', 'でしょう', 'たが', 'れる', 'られる',
        ]
        if not any(bg in text for bg in grammar_bigrams):
            return True

    return False

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
    return comments[:30], len(comments)  # 样本最多30条；同时保留过滤后的真实评论数

def main():
    print(f"🔍 5ch-roast: 抓取前{N_THREADS}条热帖...")
    threads = get_hot_threads(N_THREADS)
    if not threads:
        print("❌ 热帖列表为空，停止写入 raw_data.json")
        return 1
    results = []
    for i, t in enumerate(threads):
        print(f"  [{i+1}/{len(threads)}] {t['title'][:50]}...", end=' ')
        try:
            t['comments'], t['comment_count'] = get_comments(t['url'])
            t['comment_sample_count'] = len(t['comments'])
            print(f"{t['comment_count']}评 / 样本{t['comment_sample_count']}")
        except Exception as e:
            print(f"失败: {e}")
            t['comments'], t['comment_count'], t['comment_sample_count'] = [], 0, 0
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
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
