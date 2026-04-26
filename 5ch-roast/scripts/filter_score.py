#!/usr/bin/env python3
"""
5ch-roast filter + pre-scorer
读取 raw_data.json，过滤无聊帖，对剩余帖按逆天潜力打分排序
输出 scored.json（候选帖）和 filter_report.txt（被过滤原因）
"""
import json
import re
import os
import glob
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

# ── 配置 ──────────────────────────────────────────
MAX_CANDIDATES = 50   # 最多保留多少候选给 AI 筛选

# ── 无聊帖判定规则 ──────────────────────────────

def _tv_live_patterns(title, board, comments):
    """电视实况打卡串"""
    # 标题以 ★数字 结尾且无实质内容
    if re.search(r'★\d+$', title) and len(title) < 30:
        return True
    # 纯番組表搬运：标题只是频道名+数字
    if re.match(r'^(NHK|BS|フジ|TBS|テレ朝|日テレ|テレ東|tvk|MX|関西).*\d{3,}$', title):
        return True
    # 评论以 いちおつ 佔比过高 (>60%)
    if comments:
        otsu = sum(1 for c in comments if 'おつ' in c['text'] and len(c['text']) < 30)
        if otsu / len(comments) > 0.6:
            return True
    return False

def _idol_routine(board, title):
    """偶像fan串例行更新（无炎上事件）"""
    routine_boards = {'sakurazaka46', 'NMB', 'モ娘', 'siki', 'netidol', '4sama',
                      '日向坂', 'hinatazaka46', 'nogizaka46'}
    fire_keywords = ['炎上', '騒動', '引退', '脱退', '卒業', 'スキャンダル',
                     '不倫', '熱愛', '文春', '暴露', '事件']
    if board in routine_boards:
        if not any(kw in title for kw in fire_keywords):
            return True
    return False

def _sports_routine(board, title):
    """纯体育实况（无戏剧性事件）"""
    sport_boards = {'野球', '競馬', 'モータースポーツ'}
    drama_kw = ['骨折', '離脱', '引退', 'トレード', '事件', '乱闘', '退場',
                '記録', '新記録', 'サヨナラ', '逆転', '衝撃']
    if board in sport_boards:
        if not any(kw in title for kw in drama_kw):
            return True
    return False

def _routine_game(board, title, comments):
    """游戏板例行串（ゲハ/ネ実/dccg 的非事件帖）"""
    routine_game_boards = {'ゲハ', 'ネ実3', 'dccg', '狼', 'mjsaloon', 'app'}
    event_kw = ['炎上', '事件', '発売', '発表', '延期', '中止', '値上げ', '終了']
    if board in routine_game_boards:
        if not any(kw in title for kw in event_kw):
            return True
    return False

def _low_effort(title, comments):
    """低信息量帖：标题太短且无评论"""
    if len(title) < 15 and len(comments) < 3:
        # 除非有 meme 标签
        if not re.search(r'(高市|悲報|朗報|緊急|速報)', title):
            return True
    return False


def should_filter(t):
    """返回 (是否过滤, 原因)"""
    title = t['title']
    board = t['board']
    comments = t.get('comments', [])

    if _tv_live_patterns(title, board, comments):
        return True, '电视实况/番組表打卡'
    if _idol_routine(board, title):
        return True, '偶像例行更新'
    if _sports_routine(board, title):
        return True, '体育实况无事件'
    if _routine_game(board, title, comments):
        return True, '游戏板例行串'
    if _low_effort(title, comments):
        return True, '低信息量'
    return False, ''


# ── 逆天潜力打分 ─────────────────────────────────

def score_thread(t):
    """给帖子打逆天潜力分"""
    title = t['title']
    board = t['board']
    cc = t.get('comment_count', 0)
    comments = t.get('comments', [])
    score = 0
    reasons = []

    # 板块权重
    board_weights = {'嫌儲': 4, 'VIP': 3, 'なんG': 2, '速＋': 1}
    bw = board_weights.get(board, 0)
    if bw:
        score += bw
        reasons.append(f'{board}板+{bw}')

    # Meme 标签
    meme_tags = {
        '高市速報': 5, '高市朗報': 4, '高市悲報': 4, '高市日帝': 5,
        '緊急': 3, '速報': 3, '悲報': 3, '朗報': 3,
    }
    for tag, pts in meme_tags.items():
        if tag in title:
            score += pts
            reasons.append(f'[{tag}]+{pts}')
            break  # 只计最高

    # 过量 w（笑声 = 戏剧性）
    w_count = len(re.findall(r'w{2,}', title))
    if w_count:
        pts = min(w_count, 5)
        score += pts
        reasons.append(f'w×{w_count}+{pts}')

    # 评论数
    if cc >= 50:
        score += 2
        reasons.append(f'{cc}评+2')
    elif cc == 0:
        # 0 评论但标题劲爆 = 标题党 bonus
        if any(kw in title for kw in ['殺', '死', 'セックス', '童貞', '排便', '下痢', 'ちん', 'うん']):
            score += 3
            reasons.append('0评标题党+3')

    # 标题特征
    if '?' in title or '？' in title:
        score += 1
        reasons.append('问句+1')
    if len(title) > 60:
        score += 1
        reasons.append('长标题+1')

    # 逆天关键词
    outrageous_kw = ['チョン', 'パヨ', '殺', '死刑', 'セックス', '童貞', '排便', '下痢',
                     'ちんこ', 'まんこ', 'ウンコ', 'ゲイ', 'ホモ', 'レイプ', '中出し']
    for kw in outrageous_kw:
        if kw in title.lower():
            score += 2
            reasons.append(f'关键词+2')
            break  # 同类只计一次

    # 评论有神回复特征
    if comments:
        comment_texts = ' '.join(c['text'] for c in comments[:10])
        if re.search(r'(草$|ワロタ|確定|自演|マッチポンプ)', comment_texts):
            score += 1
            reasons.append('神回复潜质+1')

    return score, reasons


# ── 主流程 ──────────────────────────────────────

def main():
    # 找最新 raw_data.json
    raw_files = sorted(glob.glob('/mnt/d/hermes/5ch-reports/*/raw_data.json'))
    if not raw_files:
        print("❌ 未找到 raw_data.json，请先运行 scraper.py")
        return
    raw_path = raw_files[-1]
    report_dir = os.path.dirname(raw_path)
    print(f"📂 读取: {raw_path}")

    with open(raw_path, 'r') as f:
        data = json.load(f)

    threads = data['threads']
    total = len(threads)
    print(f"📊 原始: {total} 条帖子\n")

    # 过滤
    kept = []
    filtered = []
    for t in threads:
        remove, reason = should_filter(t)
        if remove:
            filtered.append((t, reason))
        else:
            kept.append(t)

    print(f"🗑️  过滤: {len(filtered)} 条")
    for t, reason in filtered:
        print(f"   [{t['board']}] {t['title'][:50]}... → {reason}")

    # 打分
    for t in kept:
        score, reasons = score_thread(t)
        t['_score'] = score
        t['_reasons'] = reasons

    kept.sort(key=lambda x: -x['_score'])

    # 截取
    candidates = kept[:MAX_CANDIDATES]

    print(f"\n⭐ 候选: {len(candidates)} 条 (最高分 {candidates[0]['_score']}, 最低 {candidates[-1]['_score']})")
    print(f"{'─'*60}")
    for i, t in enumerate(candidates[:20]):
        print(f"  {i+1:2d}. [{t['board']:6s}] {t['_score']:2d}分 | {t['title'][:60]}")
        if t['_reasons']:
            print(f"      理由: {', '.join(t['_reasons'])}")

    # 保存
    scored_path = os.path.join(report_dir, 'scored.json')
    output = {
        'scored_time': datetime.now(JST).isoformat(),
        'source': raw_path,
        'total_raw': total,
        'filtered_count': len(filtered),
        'candidate_count': len(candidates),
        'candidates': candidates
    }
    with open(scored_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 保存: {scored_path}")

    # 过滤报告
    filter_path = os.path.join(report_dir, 'filter_report.txt')
    with open(filter_path, 'w', encoding='utf-8') as f:
        f.write(f"过滤报告 {datetime.now(JST).strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"{'─'*60}\n")
        f.write(f"原始: {total}  |  过滤: {len(filtered)}  |  候选: {len(candidates)}\n\n")
        f.write("已过滤:\n")
        for t, reason in filtered:
            f.write(f"  [{t['board']}] {t['title'][:60]}... → {reason}\n")
    print(f"✅ 过滤报告: {filter_path}")


if __name__ == '__main__':
    main()
