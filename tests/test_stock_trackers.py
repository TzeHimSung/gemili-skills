from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "shared" / "scripts"
US_SCRIPTS = ROOT / "us-stock-tracker" / "scripts"
CNHK_SCRIPTS = ROOT / "cnhk-stock-tracker" / "scripts"


def _load_script_module(module_name: str, path: Path, script_dir: Path):
    for name in ("common", "analysis", "daily_report", module_name):
        sys.modules.pop(name, None)
    sys.path[:0] = [str(script_dir), str(SHARED)]
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for p in (str(script_dir), str(SHARED)):
            while p in sys.path:
                sys.path.remove(p)


def _ts(yyyy_mm_dd: str) -> int:
    from datetime import datetime
    return int(datetime.fromisoformat(yyyy_mm_dd + "T15:00:00").timestamp())


def _yahoo_result() -> dict:
    return {
        "meta": {
            "shortName": "Test Inc.",
            "fiftyTwoWeekHigh": 150,
            "fiftyTwoWeekLow": 80,
        },
        "timestamp": [_ts("2026-05-06"), _ts("2026-05-07"), _ts("2026-05-08")],
        "indicators": {
            "quote": [{
                "open": [99, 100, None],
                "high": [110, 111, 999],
                "low": [90, 91, 1],
                "close": [100, 101, None],
                "volume": [1000, 2000, None],
            }]
        },
    }


def test_us_analysis_handles_empty_inputs_without_crashing():
    analysis = _load_script_module("us_analysis_under_test", US_SCRIPTS / "analysis.py", US_SCRIPTS)

    assert analysis._index_narrative([]) == "暂无指数数据"
    assert "暂无个股数据" in analysis._one_line_summary([], [])


def test_us_yahoo_parser_uses_latest_complete_ohlcv_bar_not_trailing_null_slot():
    daily = _load_script_module("us_daily_under_test", US_SCRIPTS / "daily_report.py", US_SCRIPTS)

    quote = daily._parse_yahoo_result("NVDA", _yahoo_result())

    assert quote is not None
    assert quote.price == 101
    assert quote.prev_close == 100
    assert quote.high == 111
    assert quote.low == 91
    assert quote.volume == 2000
    assert quote.time_str == str(_ts("2026-05-07"))
    assert [bar.date for bar in quote.history] == ["2026-05-06", "2026-05-07"]


def test_cnhk_yahoo_parser_uses_latest_complete_ohlcv_bar_not_trailing_null_slot():
    daily = _load_script_module("cnhk_daily_under_test", CNHK_SCRIPTS / "daily_report.py", CNHK_SCRIPTS)

    quote = daily._parse_yahoo_result("0700.HK", _yahoo_result())

    assert quote is not None
    assert quote.price == 101
    assert quote.prev_close == 100
    assert quote.high == 111
    assert quote.low == 91
    assert quote.volume == 2000
    assert quote.time_str == str(_ts("2026-05-07"))
    assert [bar.date for bar in quote.history] == ["2026-05-06", "2026-05-07"]


def test_cnhk_key_dynamics_labels_yahoo_volume_as_volume_not_turnover():
    analysis = _load_script_module("cnhk_analysis_under_test", CNHK_SCRIPTS / "analysis.py", CNHK_SCRIPTS)
    stock = analysis.StockQuote(
        ticker="688981.SS",
        name="中芯国际",
        price=100,
        change_pct=10,
        change_amt=9,
        volume=200_000_000,
    )

    dynamics = analysis._key_dynamics([stock], [])
    joined = "\n".join(dynamics)

    assert "成交量" in joined
    assert "成交额" not in joined


def test_us_market_status_rejects_stale_data_on_expected_trading_day():
    from datetime import date

    daily = _load_script_module("us_daily_status_under_test", US_SCRIPTS / "daily_report.py", US_SCRIPTS)
    stale_quote = daily.StockQuote(
        ticker="NVDA",
        name="NVIDIA",
        price=100,
        change_pct=0,
        change_amt=0,
        time_str=str(_ts("2026-05-08")),
    )

    status = daily._check_market_status([stale_quote], [], today=date(2026, 5, 12))

    assert status["open"] is False
    assert status["last_trade_date"] == date(2026, 5, 8)
    assert "预期交易日 2026-05-11" in status["reason"]
    assert "实际最新 2026-05-08" in status["reason"]


def test_cnhk_market_status_does_not_close_mixed_report_for_hk_only_holiday():
    from datetime import date

    daily = _load_script_module("cnhk_daily_status_under_test", CNHK_SCRIPTS / "daily_report.py", CNHK_SCRIPTS)
    a_quote = daily.StockQuote(
        ticker="688981.SS",
        name="中芯国际",
        price=100,
        change_pct=0,
        change_amt=0,
        time_str=str(_ts("2026-04-03")),
    )
    hk_quote = daily.StockQuote(
        ticker="0700.HK",
        name="腾讯控股",
        price=100,
        change_pct=0,
        change_amt=0,
        time_str=str(_ts("2026-04-02")),
    )

    mixed_status = daily._check_market_status(
        [a_quote, hk_quote], [], today=date(2026, 4, 3), requested_markets={"A股", "港股"}
    )
    hk_only_status = daily._check_market_status([hk_quote], [], today=date(2026, 4, 3))

    assert mixed_status["open"] is True
    assert mixed_status["last_trade_date"] == date(2026, 4, 3)
    assert mixed_status["open_markets"] == ["A股"]
    assert mixed_status["closed_markets"] == ["港股"]
    assert mixed_status["by_market"]["港股"]["open"] is False
    assert "耶稣受难日" in mixed_status["by_market"]["港股"]["reason"]
    filtered_stocks, filtered_indices = daily._filter_quotes_by_markets(
        [a_quote, hk_quote], [], set(mixed_status["open_markets"])
    )
    assert [s.ticker for s in filtered_stocks] == ["688981.SS"]
    assert filtered_indices == []
    assert hk_only_status["open"] is False
    assert "节假日休市" in hk_only_status["reason"]
    assert "耶稣受难日" in hk_only_status["reason"]


def test_cnhk_requested_mixed_report_flags_missing_market_data_instead_of_silent_downgrade():
    from datetime import date

    daily = _load_script_module("cnhk_daily_missing_market_under_test", CNHK_SCRIPTS / "daily_report.py", CNHK_SCRIPTS)
    a_quote = daily.StockQuote(
        ticker="688981.SS",
        name="中芯国际",
        price=100,
        change_pct=0,
        change_amt=0,
        time_str=str(_ts("2026-04-08")),
    )

    status = daily._check_market_status(
        [a_quote], [], today=date(2026, 4, 8), requested_markets={"A股", "港股"}
    )

    assert status["open"] is False
    assert status["data_issue"] is True
    assert status["open_markets"] == ["A股"]
    assert status["closed_markets"] == ["港股"]
    assert status["by_market"]["港股"]["reason"] == "无行情数据"
    assert "港股无行情数据" in status["reason"]


def test_cnhk_closed_reason_does_not_claim_single_market_holiday_closes_all_cnhk():
    from datetime import date

    daily = _load_script_module("cnhk_daily_closed_reason_under_test", CNHK_SCRIPTS / "daily_report.py", CNHK_SCRIPTS)

    reason = daily._closed_reason(date(2026, 4, 3), 0, "中港")

    assert "港股因**耶稣受难日**休市" in reason
    assert "中港因**耶稣受难日**休市" not in reason
    assert "A股未列入官方休市" in reason


def test_cnhk_closed_report_text_does_not_say_last_night():
    daily_src = (CNHK_SCRIPTS / "daily_report.py").read_text(encoding="utf-8")

    assert "昨晚中港市场未开盘" not in daily_src
    assert "本交易日请求的中港市场未开盘" in daily_src


def test_cnhk_custom_dot_ss_stock_ticker_is_not_classified_as_index():
    daily = _load_script_module("cnhk_daily_custom_ticker_under_test", CNHK_SCRIPTS / "daily_report.py", CNHK_SCRIPTS)
    result = _yahoo_result()
    result["meta"]["shortName"] = "Kweichow Moutai"

    quote = daily._parse_yahoo_result("600519.SS", result)

    assert quote is not None
    assert type(quote).__name__ == "StockQuote"
    assert quote.ticker == "600519.SS"
    assert quote.price == 101


def test_stock_tracker_custom_tickers_are_stripped_before_classification():
    us_daily = _load_script_module("us_daily_ticker_split_under_test", US_SCRIPTS / "daily_report.py", US_SCRIPTS)
    us_snapshot = _load_script_module("us_snapshot_ticker_split_under_test", US_SCRIPTS / "snapshot.py", US_SCRIPTS)
    cnhk_daily = _load_script_module("cnhk_daily_ticker_split_under_test", CNHK_SCRIPTS / "daily_report.py", CNHK_SCRIPTS)
    cnhk_snapshot = _load_script_module("cnhk_snapshot_ticker_split_under_test", CNHK_SCRIPTS / "snapshot.py", CNHK_SCRIPTS)

    assert us_daily._split_custom_tickers(" NVDA, ^IXIC , msft ,, ") == (["NVDA", "MSFT"], ["^IXIC"])
    assert us_snapshot._split_custom_tickers(" gb_nvda, int_nasdaq ,, ") == (["gb_nvda"], ["int_nasdaq"])
    assert cnhk_daily._split_custom_tickers(" 0700.HK, ^HSI , 600519.SS ,, ") == (["0700.HK", "600519.SS"], ["^HSI"])
    assert cnhk_snapshot._split_custom_tickers(" sh688981, int_hangseng , hk00700 ,, ") == ["sh688981", "int_hangseng", "hk00700"]


def test_cnhk_snapshot_uses_https_for_sina_endpoint():
    snapshot = _load_script_module("cnhk_snapshot_https_under_test", CNHK_SCRIPTS / "snapshot.py", CNHK_SCRIPTS)

    assert snapshot.SINA_URL.startswith("https://hq.sinajs.cn/")


def test_stock_weixin_summary_contains_indices_movers_and_summary():
    sys.path.insert(0, str(SHARED))
    try:
        from stock_weixin_summary import render_stock_weixin_summary
    finally:
        sys.path.remove(str(SHARED))

    report_data = {
        "fetched_at": "2026-07-23T16:10:00",
        "market_open": True,
        "indices": [
            {"name": "S&P 500", "price": 7498.96, "change_pct": -0.14},
            {"name": "NASDAQ", "price": 25690.90, "change_pct": -0.57},
        ],
        "stocks": [
            {"name": "Alpha", "price": 100, "change_pct": 8.5},
            {"name": "Beta", "price": 90, "change_pct": -7.2},
            {"name": "Gamma", "price": 80, "change_pct": 2.1},
        ],
    }

    summary = render_stock_weixin_summary(report_data, title="美股收盘摘要")

    assert len(summary) <= 1800
    assert "美股收盘摘要" in summary
    assert "指数" in summary
    assert "异动" in summary
    assert "Alpha" in summary
    assert "Beta" in summary
    assert "总结" in summary
    assert "完整报告已发送至 Telegram" in summary
