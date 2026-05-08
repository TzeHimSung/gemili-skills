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
