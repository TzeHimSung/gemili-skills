#!/usr/bin/env python3
"""Generate 5ch-roast markdown report from scraped raw_data.json.
Reads latest raw_data.json from D:/hermes/5ch-reports/ and writes report.md.
The actual screening, translation, and commentary are done by AI — this script just does markdown formatting."""
import json, os, shutil, glob
from datetime import datetime

# Find latest raw_data.json
raw_files = sorted(glob.glob('/mnt/d/hermes/5ch-reports/*/raw_data.json'))
if not raw_files:
    raise SystemExit('No raw_data.json found. Run scraper.py first.')
raw_path = raw_files[-1]
print(f'Reading: {raw_path}')
with open(raw_path, 'r') as f:
    data = json.load(f)

# SELECTIONS: list of (title_substring, chinese_title, roast_text)
# Use title_substring to match — more robust than index references
selections = []  # TODO: AI fills this

# Resolve selections to thread indices by title matching
resolved = []
for title_sub, cn_title, roast in selections:
    for i, t in enumerate(data['threads']):
        if title_sub in t['title']:
            resolved.append((i, cn_title, roast))
            break
    else:
        print(f"WARNING: title '{title_sub[:40]}' not found in raw data")

# ---- Build report ----
lines = []
today = datetime.now().strftime('%Y年%m月%d日')
date_dir = datetime.now().strftime('%Y-%m-%d')

lines.append(f"# 🔥 5ch 锐评老日 — {today}")
lines.append(f"> 从 {len(data['threads'])} 条热帖中海选 {len(resolved)} 条最逆天内容")
lines.append("")

lines.append("## 📊 统计速览")
total_cc = sum(t['comment_count'] for t in data['threads'])
lines.append(f"- 热帖：{len(data['threads'])} 条 | 评论：{total_cc:,} 条 | 入选：{len(selections)} 条")

boards = {}
for t in data['threads']:
    b = t['board']
    boards[b] = boards.get(b, 0) + 1
for b, cnt in sorted(boards.items(), key=lambda x: -x[1])[:6]:
    lines.append(f"- {b}：{cnt}帖")
lines.append("")

lines.append("## 🏆 逆天排行榜")
lines.append("")

for rank, (idx, cn_title, roast) in enumerate(resolved):
    t = data['threads'][idx]
    lines.append(f"## {rank+1}. [{t['board']}] {t['title']}（{cn_title}）")
    lines.append(f"> 📊 {t['comment_count']}评论 | 🔗 {t['url']}")
    lines.append("")
    lines.append(roast)
    lines.append("")
    samples = [c['text'][:100] for c in t['comments'][:3]]
    if samples:
        lines.append("**评论区：**")
        for sc in samples:
            lines.append(f"> 「{sc}」")
        lines.append("")
    lines.append("---")
    lines.append("")

# Full index
lines.append("## 📝 完整热帖索引")
selected_indices = {s[0] for s in resolved}
for i, t in enumerate(data['threads']):
    star = ' ⭐' if i in selected_indices else ''
    lines.append(f"{i+1}. [{t['board']}] {t['title'][:55]}... — {t['comment_count']}评{star}")

report = '\n'.join(lines)

report_dir = os.path.dirname(raw_path)
report_path = os.path.join(report_dir, 'report.md')
with open(report_path, 'w', encoding='utf-8') as f:
    f.write(report)

# Backup scraper
scraper_src = os.path.expanduser('~/.hermes/skills/5ch-roast/scripts/scraper.py')
if os.path.exists(scraper_src):
    shutil.copy(scraper_src, os.path.join(report_dir, 'scraper.py'))

print(f'✅ Report: {report_path} ({len(report):,} chars)')
