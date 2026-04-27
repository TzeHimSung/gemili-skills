#!/usr/bin/env python3
"""
5ch-roast Report Generator
读取 scored.json（filter_score.py 输出），生成结构化 Markdown 报告。

如果 scored.json 中的帖子有 _ai_commentary 字段（由 AI agent 预先写入），
则自动填入锐评内容；否则只输出框架（标题 + 评论区 + 统计，供 AI 后续编辑）。

用法：
    python3 gen_report.py [--scored scored.json] [--output report.md] [--top 20]
"""
import json
import os
import re
import sys
import glob
import argparse
from datetime import datetime, timezone, timedelta

# ═══════════════════════════════════════════════════
# 5ch 板块特征描述
# ═══════════════════════════════════════════════════

JST = timezone(timedelta(hours=9))
BASE_DIR = os.environ.get('HERMES_5CH_REPORT_DIR', '/mnt/d/hermes/5ch-reports')

BOARD_INFO: dict[str, str] = {
    "嫌儲": "政治吐槽大本营，万物转高市/安倍，阴阳怪气浓度最高",
    "速＋": "新闻速报+，相对正经但评论区不正经",
    "VIP": "混沌杂谈，讨论方向完全随机，经常性癖暴露",
    "なんG": "棒球民+各种奇奇怪怪话题",
    "芸＋": "艺能新闻，炎上事件必上",
    "ゲハ": "游戏硬件战争，平台fanboy互咬",
    "netidol": "VTuber/网络偶像",
}

# 板块权重（统计展示用）
BOARD_WEIGHTS: dict[str, int] = {"嫌儲": 4, "VIP": 3, "なんG": 2, "速＋": 1}


def main():
    parser = argparse.ArgumentParser(description="5ch-roast 报告生成器")
    parser.add_argument("--scored", default="", help="scored.json 路径（默认自动找最新）")
    parser.add_argument("--output", "-o", default="", help="输出路径（默认 scored.json 同目录 report.md）")
    parser.add_argument("--top", type=int, default=20, help="入选条数（默认 20）")
    args = parser.parse_args()

    # ── 找 scored.json ──
    scored_path = args.scored
    if not scored_path:
        today_scored = os.path.join(BASE_DIR, datetime.now(JST).strftime("%Y-%m-%d"), "scored.json")
        if os.path.exists(today_scored):
            scored_files = [today_scored]
        else:
            scored_files = sorted(glob.glob(os.path.join(BASE_DIR, "*", "scored.json")))
        if not scored_files:
            print("❌ 未找到 scored.json，请先运行 filter_score.py", file=sys.stderr)
            sys.exit(1)
        scored_path = scored_files[-1]

    print(f"📂 读取: {scored_path}", file=sys.stderr)

    with open(scored_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    candidates = data.get("candidates", [])
    if not candidates:
        print("❌ scored.json 中无 candidate 数据", file=sys.stderr)
        sys.exit(1)

    # ── 取 Top N ──
    selected = candidates[: args.top]

    # ── 确定输出路径 ──
    report_dir = os.path.dirname(scored_path)
    output_path = args.output or os.path.join(report_dir, "report.md")

    # ── 生成报告 ──
    scored_time = data.get("scored_time", "")
    try:
        source_dt = datetime.fromisoformat(scored_time)
    except (TypeError, ValueError):
        source_dt = datetime.now(JST)
    today = source_dt.astimezone(JST).strftime("%Y年%m月%d日")
    total_raw = data.get("total_raw", len(candidates) + data.get("filtered_count", 0))
    filtered_count = data.get("filtered_count", 0)

    lines = []
    lines.append(f"# 🔥 5ch 锐评老日 — {today}")
    lines.append(f"> 从 {total_raw} 条热帖中海选 {len(selected)} 条最逆天内容")
    lines.append("")

    # ── 统计速览 ──
    lines.append("## 📊 统计速览")
    total_cc = sum(t.get("comment_count", 0) for t in selected)
    lines.append(f"- 热帖：{total_raw} 条 | 过滤：{filtered_count} 条 | 候选：{len(candidates)} 条 | 入选：{len(selected)} 条")
    lines.append(f"- 入选帖合计评论：{total_cc:,} 条")
    lines.append(f"- 数据时间：{data.get('scored_time', '未知')}")

    # 板块分布
    boards = {}
    for t in selected:
        b = t.get("board", "未知")
        boards[b] = boards.get(b, 0) + 1
    lines.append("")
    lines.append("**板块分布：**")
    for b, cnt in sorted(boards.items(), key=lambda x: -x[1]):
        info = BOARD_INFO.get(b, "")
        info_str = f" — {info}" if info else ""
        lines.append(f"- {b}：{cnt} 条{info_str}")
    lines.append("")

    # ── 逆天排行榜 ──
    lines.append("## 🏆 逆天排行榜")
    lines.append("")

    for rank, t in enumerate(selected):
        title = t.get("title", "无标题")
        board = t.get("board", "未知")
        url = t.get("url", "")
        cc = t.get("comment_count", 0)
        score = t.get("_score", 0)
        cn_title = t.get("_cn_title", "")

        # 标题行
        title_line = f"## {rank+1}. [{board}] {title}"
        if cn_title:
            title_line += f"（{cn_title}）"
        lines.append(title_line)
        lines.append(f"> 📊 {cc} 评论 | ⭐ 逆天分 {score} | 🔗 {url}")
        lines.append("")

        # AI 锐评（如果有）
        commentary = t.get("_ai_commentary", "")
        if commentary:
            lines.append(commentary)
            lines.append("")
        else:
            lines.append("> ⚠️ *AI 锐评待补 — 请编辑 scored.json 添加 `_ai_commentary` 字段后重新运行*")
            lines.append("")

        # 评论区精选
        comments = t.get("comments", [])
        # 评论区精选（仅去重 + 过短过滤，不再做内容过滤）
        valid_comments = []
        for c in comments:
            text = c.get("text", "")
            if len(text) < 3:
                continue
            if any(vc.get("text", "")[:30] == text[:30] for vc in valid_comments):
                continue  # 去重
            valid_comments.append(c)

        if valid_comments:
            lines.append("**评论区精选：**")
            for c in valid_comments[:3]:
                text = c["text"][:200]
                uid = c.get("uid", "名無し")
                lines.append(f"> 🗣️ `{uid}`：{text}")
            lines.append("")

        lines.append("---")
        lines.append("")

    report = "\n".join(lines)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"✅ 报告: {output_path} ({len(report):,} chars, {len(selected)} 条入选)", file=sys.stderr)

    # 同时输出到 stdout
    print(report)


if __name__ == "__main__":
    main()
