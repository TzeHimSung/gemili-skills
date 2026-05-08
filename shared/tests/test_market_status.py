from datetime import date, datetime
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from stock_tracker_lib import StockQuote, check_market_status  # noqa: E402


def _quote_on(day: date) -> StockQuote:
    ts = int(datetime(day.year, day.month, day.day, 15, 0).timestamp())
    return StockQuote(
        ticker="TEST",
        name="Test",
        price=100,
        change_pct=1,
        change_amt=1,
        time_str=str(ts),
    )


def _hours(trade_date: date, with_date: bool = True) -> str:
    return f"hours:{trade_date}:{with_date}"


def test_check_market_status_does_not_treat_friday_data_as_open_on_weekend():
    status = check_market_status(
        [_quote_on(date(2026, 5, 8))],
        [],
        hours_fn=_hours,
        today=date(2026, 5, 9),
        holidays={},
        market="中港",
    )

    assert status["open"] is False
    assert status["last_trade_date"] == date(2026, 5, 8)
    assert "周末" in status["reason"]


def test_check_market_status_does_not_treat_old_data_as_open_on_holiday():
    status = check_market_status(
        [_quote_on(date(2026, 4, 30))],
        [],
        hours_fn=_hours,
        today=date(2026, 5, 1),
        holidays={date(2026, 5, 1): "劳动节假期"},
        market="A股",
    )

    assert status["open"] is False
    assert status["last_trade_date"] == date(2026, 4, 30)
    assert "劳动节假期" in status["reason"]


def test_check_market_status_requires_latest_data_from_current_trading_day():
    stale = check_market_status(
        [_quote_on(date(2026, 5, 7))],
        [],
        hours_fn=_hours,
        today=date(2026, 5, 8),
        holidays={},
        market="中港",
    )
    fresh = check_market_status(
        [_quote_on(date(2026, 5, 8))],
        [],
        hours_fn=_hours,
        today=date(2026, 5, 8),
        holidays={},
        market="中港",
    )

    assert stale["open"] is False
    assert "数据延迟" in stale["reason"]
    assert fresh["open"] is True
    assert fresh["last_trade_date"] == date(2026, 5, 8)
