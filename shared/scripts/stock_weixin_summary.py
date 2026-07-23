#!/usr/bin/env python3
"""Render a deterministic single-message stock-market summary for Weixin."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from cron_rate_safe_delivery import DEFAULT_MAX_WEIXIN_CHARS, compact_weixin_text


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _change_icon(value: float) -> str:
    return "🟢" if value >= 0 else "🔴"


def render_stock_weixin_summary(
    report_data: dict[str, Any],
    *,
    title: str,
    max_chars: int = DEFAULT_MAX_WEIXIN_CHARS,
) -> str:
    fetched_at = str(report_data.get("fetched_at") or "")
    date_label = fetched_at[:10] or "今日"
    # A Markdown heading also prevents Hermes' short-chat formatter from
    # splitting a small closed-market digest into several Weixin bubbles.
    lines = [f"# 📊 {title} — {date_label}", ""]

    if report_data.get("market_open") is False:
        reason = str(
            report_data.get("market_reason")
            or report_data.get("reason")
            or "市场休市或数据暂不可用"
        ).strip()
        lines.extend(
            [
                "🏖️ 市场状态",
                reason,
                "",
                "完整报告已发送至 Telegram。",
            ]
        )
        return compact_weixin_text("\n".join(lines), max_chars=max_chars)

    indices = list(report_data.get("indices") or [])
    stocks = list(report_data.get("stocks") or [])

    lines.append("📈 指数")
    for item in indices[:5]:
        change = _number(item.get("change_pct"))
        price = _number(item.get("price"))
        lines.append(
            f"- {_change_icon(change)} {item.get('name') or item.get('ticker')}: "
            f"{price:,.2f} ({change:+.2f}%)"
        )
    if not indices:
        lines.append("- 暂无指数数据")

    lines.extend(["", "🔥 异动"])
    movers = sorted(
        stocks,
        key=lambda item: abs(_number(item.get("change_pct"))),
        reverse=True,
    )[:6]
    for item in movers:
        change = _number(item.get("change_pct"))
        lines.append(
            f"- {_change_icon(change)} {item.get('name') or item.get('ticker')}: "
            f"{change:+.2f}%"
        )
    if not movers:
        lines.append("- 暂无个股数据")

    up = sum(1 for item in stocks if _number(item.get("change_pct")) > 0)
    down = sum(1 for item in stocks if _number(item.get("change_pct")) < 0)
    flat = max(0, len(stocks) - up - down)
    if up > down:
        direction = "上涨家数占优"
    elif down > up:
        direction = "下跌家数占优"
    else:
        direction = "涨跌数量接近"
    lines.extend(
        [
            "",
            "🧭 总结",
            f"{direction}：上涨 {up}、下跌 {down}、持平 {flat}。",
            "",
            "完整报告已发送至 Telegram。",
        ]
    )
    return compact_weixin_text("\n".join(lines), max_chars=max_chars)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a compact Weixin stock summary")
    parser.add_argument("--input", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--output")
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_WEIXIN_CHARS)
    args = parser.parse_args(argv)

    report_data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    summary = render_stock_weixin_summary(
        report_data,
        title=args.title,
        max_chars=args.max_chars,
    )
    if args.output:
        Path(args.output).write_text(summary + "\n", encoding="utf-8")
    else:
        print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
