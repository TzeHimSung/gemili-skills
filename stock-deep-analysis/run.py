#!/usr/bin/env python3
"""Repo-local CLI wrapper for stock-deep-analysis.

This file intentionally lives at the skill root so tests and humans never depend
on an upstream checkout root such as /home/jhseng/run.py.  It delegates to the
legacy scripts/ entrypoint by default, while keeping the opt-in v3 pipeline path
available through UZI_PIPELINE=1.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Sequence

SKILL_ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = SKILL_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _get_version() -> str:
    """Read the displayed version from SKILL.md instead of hardcoding it."""

    skill_md = SKILL_ROOT / "SKILL.md"
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    match = re.search(r"Stock Deep Analysis .*? v([0-9][^\s]*)", text)
    return match.group(1) if match else "unknown"


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Stock Deep Analysis v{_get_version()}")
    parser.add_argument("ticker", nargs="?", default="002273.SZ", help="股票代码或名称")
    parser.add_argument("--no-browser", action="store_true", help="生成报告后不自动打开浏览器")
    parser.add_argument("--no-resume", action="store_true", help="忽略现有 .cache，强制重新采集")
    parser.add_argument("--depth", choices=("lite", "deep"), help="分析深度，写入 UZI_DEPTH")
    parser.add_argument("--remote", action="store_true", help="兼容旧文档参数；当前 wrapper 不自动启动 tunnel")
    return parser.parse_args(argv)


def _apply_cli_env(args: argparse.Namespace) -> None:
    # CLI direct runs do not have an agent-authored analysis pass; downgrade the
    # missing-agent-analysis self-review finding so HTML can still render.
    os.environ.setdefault("UZI_CLI_ONLY", "1")
    if args.no_browser:
        os.environ["UZI_NO_AUTO_OPEN"] = "1"
    if args.no_resume:
        os.environ["UZI_NO_RESUME"] = "1"
    if args.depth:
        os.environ["UZI_DEPTH"] = args.depth


def _pipeline_succeeded(args: argparse.Namespace) -> bool:
    """Run opt-in v3 pipeline, returning False to trigger legacy fallback."""

    if os.environ.get("UZI_PIPELINE") != "1":
        return False
    try:
        from lib.pipeline import run_pipeline  # type: ignore[reportMissingImports]

        run_pipeline(args.ticker, resume=not args.no_resume)
        return True
    except Exception as exc:  # pragma: no cover - source-level regression tests cover fallback contract
        print(f"⚠️ pipeline failed，回退 legacy: {exc}", file=sys.stderr)
        return False


def run_analysis(ticker: str):
    """Run the legacy stage1 + stage2 flow."""

    from run_real_test import main as legacy_main  # type: ignore[reportMissingImports]

    return legacy_main(ticker)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    _apply_cli_env(args)
    print(f"Stock Deep Analysis v{_get_version()} · {args.ticker}")
    if _pipeline_succeeded(args):
        return 0
    run_analysis(args.ticker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
