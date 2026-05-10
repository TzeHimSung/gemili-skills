#!/usr/bin/env python3
"""
Anison Live 倒计时 — 一键执行入口
用法:
    python3 scripts/run_all.py              # 完整流程：爬取 + 生成报表
    python3 scripts/run_all.py --skip-scrape # 仅用已有数据生成报表

输出:
    data/bandori.json
    data/lovelive.json
    report.md  (通用版)
    report_telegram.md  (Telegram 兼容版)
"""

import sys
from pathlib import Path

# 确保 common 模块可导入
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from common import save_events


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Anison Live 倒计时报表生成",
    )
    parser.add_argument(
        "--skip-scrape",
        action="store_true",
        help="跳过数据爬取，仅用已有数据生成报表",
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="数据/输出目录 (默认: data/)",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 1: 爬取 ──
    if not args.skip_scrape:
        print("=" * 50, file=sys.stderr)
        print("Step 1: 爬取各企划数据", file=sys.stderr)
        print("=" * 50, file=sys.stderr)

        # BanG Dream
        print("\n🎸 BanG Dream!", file=sys.stderr)
        from scrape_bangdream import scrape as scrape_bd
        bd_events = scrape_bd()
        save_events(bd_events, str(data_dir / "bandori.json"))

        # LoveLive
        print("\n🎤 LoveLive!", file=sys.stderr)
        from scrape_lovelive import scrape_all as scrape_ll
        ll_events = scrape_ll()
        save_events(ll_events, str(data_dir / "lovelive.json"))

        total = len(bd_events) + len(ll_events)
        print(
            f"\n📊 合计: BanG Dream {len(bd_events)} + "
            f"LoveLive {len(ll_events)} = {total} 条",
            file=sys.stderr,
        )

    # ── Step 2: 生成报表 ──
    print("\n" + "=" * 50, file=sys.stderr)
    print("Step 2: 生成报表", file=sys.stderr)
    print("=" * 50, file=sys.stderr)

    from generate_report import generate_markdown

    # 通用版（微信 / QQ）
    report_general = generate_markdown(str(data_dir), platform="general")
    (data_dir / "report.md").write_text(report_general, encoding="utf-8")
    print("  ✅ report.md (通用)", file=sys.stderr)

    # Telegram 兼容版
    report_tg = generate_markdown(str(data_dir), platform="telegram")
    (data_dir / "report_telegram.md").write_text(report_tg, encoding="utf-8")
    print("  ✅ report_telegram.md (Telegram)", file=sys.stderr)

    # 同时输出到 stdout 供 cron 捕获
    print("\n" + report_general)


if __name__ == "__main__":
    main()
