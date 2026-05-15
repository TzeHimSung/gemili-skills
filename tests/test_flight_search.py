from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FLIGHT_SEARCH = ROOT / "flight-search" / "scripts" / "flight_search.py"


def _load_flight_search():
    spec = importlib.util.spec_from_file_location("flight_search_under_test", FLIGHT_SEARCH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["flight_search_under_test"] = module
    spec.loader.exec_module(module)
    return module


def _record(fs, *, direction: str, flight_number: str):
    return fs.FlightRecord(
        direction=direction,
        date="2026-05-14",
        operating_flight=flight_number,
        marketing_flights=[flight_number],
        operating_airline="Test Air",
        departure_airport="CAN" if direction == "outbound" else "HND",
        departure_airport_name="",
        departure_terminal="",
        departure_gate="",
        departure_time_local="10:00",
        departure_timezone="CST" if direction == "outbound" else "JST",
        arrival_airport="HND" if direction == "outbound" else "CAN",
        arrival_airport_name="",
        arrival_terminal="",
        arrival_gate="",
        arrival_time_local="14:00",
        arrival_timezone="JST" if direction == "outbound" else "CST",
        duration="",
        aircraft="",
        aircraft_iata="",
    )


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


def test_normalize_iata_accepts_documented_aliases_and_rejects_unknowns():
    fs = _load_flight_search()

    assert fs.normalize_iata("广州") == "CAN"
    assert fs.normalize_iata("東京") == "TYO"
    assert fs.normalize_iata("羽田") == "HND"
    assert fs.normalize_iata("can") == "CAN"
    with pytest.raises(ValueError):
        fs.normalize_iata("不存在机场")


def test_fetch_amadeus_requests_nonstop_and_ignores_connecting_itineraries(monkeypatch):
    fs = _load_flight_search()
    requested_urls = []
    payload = {
        "data": [
            {
                "price": {"grandTotal": "800", "currency": "CNY"},
                "itineraries": [
                    {
                        "segments": [
                            {"id": "1", "carrierCode": "CZ", "number": "385"},
                            {"id": "2", "carrierCode": "NH", "number": "98"},
                        ]
                    }
                ],
                "travelerPricings": [{"fareDetailsBySegment": []}],
            }
        ]
    }

    monkeypatch.setattr(fs, "amadeus_token", lambda: "token")

    def fake_urlopen(req, timeout=30):
        requested_urls.append(req.full_url)
        return _FakeResponse(payload)

    monkeypatch.setattr(fs.urllib.request, "urlopen", fake_urlopen)

    offers = fs.fetch_amadeus_prices("CAN", "HND", "2026-05-14", "", 1, "ECONOMY", "CNY")

    assert requested_urls
    assert "nonStop=true" in requested_urls[0]
    assert offers == []


def test_fetch_amadeus_roundtrip_rejects_mixed_direct_and_connecting_offer(monkeypatch):
    fs = _load_flight_search()
    payload = {
        "data": [
            {
                "price": {"grandTotal": "1200", "currency": "CNY"},
                "itineraries": [
                    {"segments": [{"id": "1", "carrierCode": "CZ", "number": "385", "departure": {"iataCode": "CAN"}, "arrival": {"iataCode": "HND"}}]},
                    {"segments": [
                        {"id": "2", "carrierCode": "NH", "number": "97", "departure": {"iataCode": "HND"}, "arrival": {"iataCode": "ICN"}},
                        {"id": "3", "carrierCode": "CZ", "number": "306", "departure": {"iataCode": "ICN"}, "arrival": {"iataCode": "CAN"}},
                    ]},
                ],
                "travelerPricings": [{"fareDetailsBySegment": []}],
            }
        ]
    }

    monkeypatch.setattr(fs, "amadeus_token", lambda: "token")
    monkeypatch.setattr(fs.urllib.request, "urlopen", lambda req, timeout=30: _FakeResponse(payload))

    offers = fs.fetch_amadeus_prices("CAN", "HND", "2026-05-14", "2026-05-20", 1, "ECONOMY", "CNY")

    assert offers == []


def test_fetch_kiwi_requests_zero_stopovers_and_ignores_connecting_routes(monkeypatch):
    fs = _load_flight_search()
    requested_urls = []
    payload = {
        "data": [
            {
                "price": 980,
                "deep_link": "https://kiwi.example/connecting",
                "route": [
                    {"airline": "CZ", "flight_no": 301, "flyFrom": "CAN", "flyTo": "ICN", "return": 0},
                    {"airline": "KE", "flight_no": 720, "flyFrom": "ICN", "flyTo": "HND", "return": 0},
                ],
            }
        ]
    }

    monkeypatch.setenv("TEQUILA_API_KEY", "test-key")

    def fake_urlopen(req, timeout=30):
        requested_urls.append(req.full_url)
        return _FakeResponse(payload)

    monkeypatch.setattr(fs.urllib.request, "urlopen", fake_urlopen)

    offers = fs.fetch_kiwi_prices("CAN", "HND", "2026-05-14", "", 1, "ECONOMY", "CNY")

    assert requested_urls
    assert "max_stopovers=0" in requested_urls[0]
    assert offers == []


def test_fetch_kiwi_roundtrip_rejects_offer_missing_return_direction(monkeypatch):
    fs = _load_flight_search()
    payload = {
        "data": [
            {
                "price": 1200,
                "deep_link": "https://kiwi.example/one-leg-only",
                "route": [
                    {"airline": "CZ", "flight_no": 385, "flyFrom": "CAN", "flyTo": "HND", "return": 0},
                ],
            }
        ]
    }

    monkeypatch.setenv("TEQUILA_API_KEY", "test-key")
    monkeypatch.setattr(fs.urllib.request, "urlopen", lambda req, timeout=30: _FakeResponse(payload))

    offers = fs.fetch_kiwi_prices("CAN", "HND", "2026-05-14", "2026-05-20", 1, "ECONOMY", "CNY")

    assert offers == []


def test_fetch_kiwi_roundtrip_keeps_provider_total_without_fabricating_segment_prices(monkeypatch):
    fs = _load_flight_search()
    payload = {
        "data": [
            {
                "price": 1200,
                "deep_link": "https://kiwi.example/deep-link",
                "route": [
                    {"airline": "CZ", "flight_no": 385, "flyFrom": "CAN", "flyTo": "HND", "return": 0},
                    {"airline": "CZ", "flight_no": 386, "flyFrom": "HND", "flyTo": "CAN", "return": 1},
                ],
            }
        ]
    }

    monkeypatch.setenv("TEQUILA_API_KEY", "test-key")
    monkeypatch.setattr(fs.urllib.request, "urlopen", lambda req, timeout=30: _FakeResponse(payload))

    offers = fs.fetch_kiwi_prices("CAN", "HND", "2026-05-14", "2026-05-20", 1, "ECONOMY", "CNY")

    assert [offer.direction for offer in offers] == ["outbound", "return"]
    assert [offer.flight_number for offer in offers] == ["CZ385", "CZ386"]
    assert [offer.price for offer in offers] == [1200.0, 1200.0]
    assert [offer.total_trip_price for offer in offers] == [1200.0, 1200.0]
    assert {offer.deep_link for offer in offers} == {"https://kiwi.example/deep-link"}
    assert all("total" in offer.raw_match_note for offer in offers)
    assert all("total/" not in offer.raw_match_note for offer in offers)


def test_attach_prices_respects_offer_direction_and_adds_deep_link_sources():
    fs = _load_flight_search()
    outbound = _record(fs, direction="outbound", flight_number="ZZ100")
    ret = _record(fs, direction="return", flight_number="ZZ100")
    offers = [
        fs.PriceOffer(
            provider="Kiwi/Tequila",
            flight_number="ZZ100",
            direction="outbound",
            price=100.0,
            currency="CNY",
            deep_link="https://kiwi.example/outbound",
        ),
        fs.PriceOffer(
            provider="Kiwi/Tequila",
            flight_number="ZZ100",
            direction="return",
            price=200.0,
            currency="CNY",
            deep_link="https://kiwi.example/return",
        ),
    ]

    fs.attach_prices([outbound, ret], offers)

    assert [price.direction for price in outbound.prices] == ["outbound"]
    assert [price.price for price in outbound.prices] == [100.0]
    assert [price.direction for price in ret.prices] == ["return"]
    assert [price.price for price in ret.prices] == [200.0]
    assert any(src.url == "https://kiwi.example/outbound" and src.note == "booking deep link" for src in outbound.sources)
    assert any(src.url == "https://kiwi.example/return" and src.note == "booking deep link" for src in ret.sources)


def test_rendered_source_lines_include_deep_links_when_present():
    fs = _load_flight_search()
    outbound = _record(fs, direction="outbound", flight_number="ZZ100")
    fs.attach_prices(
        [outbound],
        [
            fs.PriceOffer(
                provider="Kiwi/Tequila",
                flight_number="ZZ100",
                direction="outbound",
                price=100.0,
                currency="CNY",
                deep_link="https://kiwi.example/outbound",
            )
        ],
    )

    rendered = fs.render_markdown(
        [outbound],
        {
            "origin": "CAN",
            "destination": "HND",
            "departure_date": "2026-05-14",
            "roundtrip": False,
            "cabin": "ECONOMY",
            "adults": 1,
            "currency": "CNY",
        },
    )

    assert "Kiwi/Tequila: https://kiwi.example/outbound (booking deep link)" in rendered


def test_rendered_price_includes_total_trip_provenance_note():
    fs = _load_flight_search()
    outbound = _record(fs, direction="outbound", flight_number="ZZ100")
    outbound.prices = [
        fs.PriceOffer(
            provider="Kiwi/Tequila",
            flight_number="ZZ100",
            direction="outbound",
            cabin="ECONOMY",
            price=1200.0,
            total_trip_price=1200.0,
            currency="CNY",
            raw_match_note="round-trip total ¥1,200.00; provider total is not a segment fare",
        )
    ]

    rendered = fs.render_markdown(
        [outbound],
        {
            "origin": "CAN",
            "destination": "HND",
            "departure_date": "2026-05-14",
            "roundtrip": False,
            "cabin": "ECONOMY",
            "adults": 1,
            "currency": "CNY",
        },
    )

    assert "人民币¥1,200" in rendered
    assert "round-trip total ¥1,200.00" in rendered
    assert "provider total is not a segment fare" in rendered


def test_price_offer_positional_constructor_preserves_original_field_order():
    fs = _load_flight_search()

    offer = fs.PriceOffer(
        "Provider",
        "ZZ100",
        "ECONOMY",
        "Y",
        "YBASIC",
        3,
        123.45,
        "CNY",
        "https://example.test/deep-link",
        "provider note",
    )

    assert offer.provider == "Provider"
    assert offer.flight_number == "ZZ100"
    assert offer.cabin == "ECONOMY"
    assert offer.booking_class == "Y"
    assert offer.fare_basis == "YBASIC"
    assert offer.seats == 3
    assert offer.price == 123.45
    assert offer.currency == "CNY"
    assert offer.deep_link == "https://example.test/deep-link"
    assert offer.raw_match_note == "provider note"
    assert offer.direction == ""
    assert offer.total_trip_price is None
