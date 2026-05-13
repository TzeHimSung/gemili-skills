#!/usr/bin/env python3
"""Direct-flight search helper for Hermes.

Collects non-stop flight schedules from FlightStats/Cirium public pages and,
when API credentials are available, cross-checks prices/cabins from shopping
APIs. It deliberately avoids bypassing OTA anti-bot challenges.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
# FlightStats route pages expose rolling time windows. Polling every 3 hours
# covers the day with overlap while avoiding the rate/legacy-shell behavior seen
# after hammering all 24 hourly URLs.
DEFAULT_ROUTE_HOURS = tuple(range(0, 24, 3))


@dataclass
class SourceRecord:
    name: str
    url: str
    note: str = ""


@dataclass
class PriceOffer:
    provider: str
    flight_number: str = ""
    cabin: str = ""
    booking_class: str = ""
    fare_basis: str = ""
    seats: Optional[int] = None
    price: Optional[float] = None
    currency: str = ""
    deep_link: str = ""
    raw_match_note: str = ""


@dataclass
class FlightRecord:
    direction: str
    date: str
    operating_flight: str
    marketing_flights: List[str]
    operating_airline: str
    departure_airport: str
    departure_airport_name: str
    departure_terminal: str
    departure_gate: str
    departure_time_local: str
    departure_timezone: str
    arrival_airport: str
    arrival_airport_name: str
    arrival_terminal: str
    arrival_gate: str
    arrival_time_local: str
    arrival_timezone: str
    duration: str
    aircraft: str
    aircraft_iata: str
    aircraft_registration: str = ""
    aircraft_age: str = ""
    status: str = ""
    status_description: str = ""
    prices: List[PriceOffer] = field(default_factory=list)
    verification: str = "single-source schedule"
    sources: List[SourceRecord] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)


def http_get(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 25) -> str:
    merged = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    }
    if headers:
        merged.update(headers)
    req = urllib.request.Request(url, headers=merged)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, "ignore")


def api_get_json(url: str, timeout: int = 25) -> Dict[str, Any]:
    text = http_get(url, headers={"Accept": "application/json"}, timeout=timeout)
    return json.loads(text)


def rqid() -> str:
    return uuid.uuid4().hex[:11]


def extract_next_data(html: str) -> Dict[str, Any]:
    marker = "__NEXT_DATA__ = "
    start = html.find(marker)
    if start == -1:
        m = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.S)
        if not m:
            raise ValueError("FlightStats __NEXT_DATA__ payload not found")
        return json.loads(m.group(1))

    s = html[start + len(marker):]
    depth = 0
    in_str = False
    esc = False
    end = None
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
    if end is None:
        raise ValueError("FlightStats __NEXT_DATA__ JSON end not found")
    return json.loads(s[:end])


def normalize_iata(code: str) -> str:
    code = (code or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{3}", code):
        raise ValueError(f"Expected 3-character IATA airport/city code, got {code!r}")
    return code


def flightstats_route_url(origin: str, dest: str, date: str, hour: int) -> str:
    y, m, d = map(int, date.split("-"))
    return (
        f"https://www.flightstats.com/v2/flight-tracker/route/{origin}/{dest}"
        f"?year={y}&month={m}&date={d}&hour={hour}"
    )


def flightstats_route_api_url(origin: str, dest: str, date: str, hour: int, num_hours: int = 6) -> str:
    y, m, d = map(int, date.split("-"))
    return (
        f"https://www.flightstats.com/v2/api-next/flight-tracker/route/{origin}/{dest}/{y}/{m}/{d}"
        f"?carrierCode=&numHours={num_hours}&rqid={rqid()}&hour={hour}"
    )


def flightstats_detail_api_url(row: Dict[str, Any]) -> str:
    c = row.get("carrier") or {}
    carrier = c.get("fs", "")
    number = c.get("flightNumber", "")
    # Route URLs carry canonical year/month/date/flightId parameters.
    parsed = urllib.parse.urlsplit(flightstats_abs_url(row["url"]))
    q = urllib.parse.parse_qs(parsed.query)
    year = (q.get("year") or [""])[0]
    month = (q.get("month") or [""])[0]
    date = (q.get("date") or [""])[0]
    flight_id = (q.get("flightId") or [""])[0]
    suffix = f"/{flight_id}" if flight_id else ""
    return (
        f"https://www.flightstats.com/v2/api-next/flight-tracker/{carrier}/{number}/{year}/{month}/{date}{suffix}"
        f"?rqid={rqid()}"
    )


def flightstats_abs_url(path_or_url: str) -> str:
    if path_or_url.startswith("http"):
        return path_or_url
    if path_or_url.startswith("/flight-tracker"):
        return "https://www.flightstats.com/v2" + path_or_url
    return "https://www.flightstats.com" + path_or_url


def fetch_next_data_url(url: str, attempts: int = 3) -> Dict[str, Any]:
    """Fetch a FlightStats page and parse its embedded JSON with light retries.

    FlightStats occasionally returns an HTML shell/challenge without the payload
    when hit too quickly. Retrying with a short backoff is usually enough and is
    still normal public-page access rather than captcha bypass.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            html = http_get(url)
            return extract_next_data(html)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(1.0 + attempt * 1.5)
    raise last_exc or RuntimeError("unknown fetch_next_data_url error")


def fetch_flightstats_route(origin: str, dest: str, date: str, pause: float = 0.25) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    all_rows: List[Dict[str, Any]] = []
    header: Dict[str, Any] = {}
    seen_payloads = set()
    errors: List[str] = []
    for hour in DEFAULT_ROUTE_HOURS:
        page_url = flightstats_route_url(origin, dest, date, hour)
        api_url = flightstats_route_api_url(origin, dest, date, hour)
        try:
            try:
                payload = api_get_json(api_url)
                route = payload.get("data") or {}
            except Exception:
                data = fetch_next_data_url(page_url)
                route = data.get("props", {}).get("initialState", {}).get("flightTracker", {}).get("route", {})
            if route.get("header"):
                header = route.get("header") or header
            rows = route.get("flights") or []
            for row in rows:
                key = row.get("url") or json.dumps(row, sort_keys=True)
                if key not in seen_payloads:
                    seen_payloads.add(key)
                    row = dict(row)
                    row["_route_source_url"] = page_url
                    row["_route_api_url"] = api_url
                    all_rows.append(row)
        except Exception as exc:  # noqa: BLE001 - keep scraping resilient
            errors.append(f"hour={hour}: {exc}")
        time.sleep(pause)
    if errors and not all_rows:
        raise RuntimeError("FlightStats route fetch failed: " + "; ".join(errors[:5]))
    return all_rows, header


def parse_operated_by(text: str) -> str:
    # Examples: "Operated by China Southern Airlines 385", "Operated by JAL 88"
    if not text:
        return ""
    m = re.search(r"Operated by\s+(.+?)\s+([A-Z0-9]{1,3})?\s*(\d+[A-Z]?)$", text, re.I)
    if m:
        maybe_code = (m.group(2) or "").upper()
        num = m.group(3)
        if maybe_code and len(maybe_code) <= 3:
            return f"{maybe_code}{num}"
        return num
    return ""


def flight_no_from_row(row: Dict[str, Any]) -> str:
    c = row.get("carrier") or {}
    return f"{c.get('fs', '')}{c.get('flightNumber', '')}".strip()


def choose_operating_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        fid = ""
        m = re.search(r"flightId=(\d+)", row.get("url", ""))
        if m:
            fid = m.group(1)
        key = fid or f"{row.get('sortTime')}|{row.get('departureTime', {}).get('time24')}|{row.get('arrivalTime', {}).get('time24')}"
        groups.setdefault(key, []).append(row)

    chosen: List[Dict[str, Any]] = []
    for group in groups.values():
        non_codeshare = [r for r in group if not r.get("isCodeshare")]
        base = non_codeshare[0] if non_codeshare else group[0]
        marketing = [flight_no_from_row(r) for r in group if flight_no_from_row(r)]
        base = dict(base)
        base["_marketing_flights"] = marketing
        chosen.append(base)
    chosen.sort(key=lambda r: r.get("sortTime") or "")
    return chosen


def fetch_flightstats_detail(row: Dict[str, Any]) -> Dict[str, Any]:
    page_url = flightstats_abs_url(row["url"])
    api_url = flightstats_detail_api_url(row)
    try:
        payload = api_get_json(api_url)
        flight = payload.get("data") or {}
        flight["_detail_source_url"] = page_url
        flight["_detail_api_url"] = api_url
        time.sleep(0.2)
        return flight
    except Exception:
        pass

    full_url = page_url
    # Detail pages can intermittently fall back to a legacy shell when the
    # flightId query parameter is present. Try both the exact route URL and the
    # canonical carrier/flight/date URL before giving up.
    parsed = urllib.parse.urlsplit(full_url)
    q = urllib.parse.parse_qs(parsed.query)
    q.pop("flightId", None)
    stripped_query = urllib.parse.urlencode({k: v[-1] for k, v in q.items()})
    stripped_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, stripped_query, parsed.fragment))
    candidates = [full_url]
    if stripped_url != full_url:
        candidates.append(stripped_url)

    last_exc: Optional[Exception] = None
    for url in candidates:
        try:
            data = fetch_next_data_url(url, attempts=2)
            flight = data.get("props", {}).get("initialState", {}).get("flightTracker", {}).get("flight") or {}
            flight["_detail_source_url"] = url
            time.sleep(0.4)
            return flight
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(1.0)
    raise last_exc or RuntimeError("FlightStats detail fetch failed")


def safe_get(d: Dict[str, Any], path: Iterable[str], default: Any = "") -> Any:
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur or cur[p] is None:
            return default
        cur = cur[p]
    return cur


def build_record(direction: str, query_date: str, row: Dict[str, Any], detail: Dict[str, Any]) -> FlightRecord:
    carrier = safe_get(detail, ["ticketHeader", "carrier"], {}) or safe_get(detail, ["resultHeader", "carrier"], {}) or row.get("carrier", {})
    operating_flight = f"{carrier.get('fs', '')}{detail.get('ticketHeader', {}).get('flightNumber') or detail.get('resultHeader', {}).get('flightNumber') or row.get('carrier', {}).get('flightNumber', '')}"
    if not operating_flight.strip():
        operating_flight = flight_no_from_row(row)
    marketing = row.get("_marketing_flights") or [operating_flight]
    for cs in detail.get("codeshares") or []:
        fn = f"{cs.get('fs', '')}{cs.get('flightNumber', '')}"
        if fn and fn not in marketing:
            marketing.append(fn)

    dep = detail.get("departureAirport") or {}
    arr = detail.get("arrivalAirport") or {}
    equip = safe_get(detail, ["additionalFlightInfo", "equipment"], {}) or {}
    status = detail.get("status") or {}

    record = FlightRecord(
        direction=direction,
        date=query_date,
        operating_flight=operating_flight,
        marketing_flights=marketing,
        operating_airline=carrier.get("name", ""),
        departure_airport=dep.get("iata") or dep.get("fs") or "",
        departure_airport_name=dep.get("name", ""),
        departure_terminal=str(dep.get("terminal") or ""),
        departure_gate=str(dep.get("gate") or ""),
        departure_time_local=safe_get(dep, ["times", "scheduled", "time24"], ""),
        departure_timezone=safe_get(dep, ["times", "scheduled", "timezone"], ""),
        arrival_airport=arr.get("iata") or arr.get("fs") or "",
        arrival_airport_name=arr.get("name", ""),
        arrival_terminal=str(arr.get("terminal") or ""),
        arrival_gate=str(arr.get("gate") or ""),
        arrival_time_local=safe_get(arr, ["times", "scheduled", "time24"], ""),
        arrival_timezone=safe_get(arr, ["times", "scheduled", "timezone"], ""),
        duration=safe_get(detail, ["additionalFlightInfo", "flightDuration"], ""),
        aircraft=equip.get("name", ""),
        aircraft_iata=equip.get("iata", ""),
        status=status.get("status", ""),
        status_description=status.get("statusDescription", ""),
        verification="FlightStats schedule/detail matched",
        sources=[
            SourceRecord("FlightStats route", row.get("_route_source_url", "")),
            SourceRecord("FlightStats detail", detail.get("_detail_source_url", "")),
        ],
    )
    # Public schedule pages usually do not expose tail/registration before operation.
    if not record.aircraft_registration:
        record.missing.append("aircraft_registration")
    if not record.aircraft_age:
        record.missing.append("aircraft_age")
    if not record.departure_terminal:
        record.missing.append("departure_terminal")
    if not record.arrival_terminal:
        record.missing.append("arrival_terminal")
    return record


def fetch_flightstats_direction(origin: str, dest: str, date: str, direction: str) -> List[FlightRecord]:
    rows, _header = fetch_flightstats_route(origin, dest, date)
    operating_rows = choose_operating_rows(rows)
    # Avoid immediately hammering detail pages after the route sweep; FlightStats
    # may otherwise return a lightweight HTML shell without embedded data.
    if operating_rows:
        time.sleep(4.0)
    records: List[FlightRecord] = []
    failed: List[Tuple[int, Dict[str, Any], Exception]] = []

    def route_only_record(row: Dict[str, Any], exc: Exception) -> FlightRecord:
        c = row.get("carrier") or {}
        return FlightRecord(
            direction=direction,
            date=date,
            operating_flight=f"{c.get('fs', '')}{c.get('flightNumber', '')}",
            marketing_flights=row.get("_marketing_flights") or [flight_no_from_row(row)],
            operating_airline=c.get("name", ""),
            departure_airport=origin,
            departure_airport_name="",
            departure_terminal="",
            departure_gate="",
            departure_time_local=safe_get(row, ["departureTime", "time24"], ""),
            departure_timezone="",
            arrival_airport=dest,
            arrival_airport_name="",
            arrival_terminal="",
            arrival_gate="",
            arrival_time_local=safe_get(row, ["arrivalTime", "time24"], ""),
            arrival_timezone="",
            duration="",
            aircraft="",
            aircraft_iata="",
            verification="FlightStats route only; detail fetch failed",
            sources=[SourceRecord("FlightStats route", row.get("_route_source_url", ""))],
            missing=["detail", f"detail_error={exc}"],
        )

    for row in operating_rows:
        try:
            detail = fetch_flightstats_detail(row)
            records.append(build_record(direction, date, row, detail))
        except Exception as exc:  # noqa: BLE001
            failed.append((len(records), row, exc))
            records.append(route_only_record(row, exc))

    # Some FlightStats detail pages intermittently serve a legacy shell on the
    # first pass but succeed a few seconds later. Do a single second pass so the
    # final report is not missing terminals/aircraft unnecessarily.
    if failed:
        time.sleep(8.0)
        for idx, row, _exc in failed:
            try:
                detail = fetch_flightstats_detail(row)
                records[idx] = build_record(direction, date, row, detail)
            except Exception:
                pass
    return records


def amadeus_token() -> Optional[str]:
    client_id = os.environ.get("AMADEUS_CLIENT_ID")
    client_secret = os.environ.get("AMADEUS_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    base = os.environ.get("AMADEUS_BASE_URL", "https://test.api.amadeus.com")
    data = urllib.parse.urlencode(
        {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}
    ).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/v1/security/oauth2/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        payload = json.loads(resp.read().decode())
        return payload.get("access_token")


def fetch_amadeus_prices(origin: str, dest: str, departure_date: str, return_date: str, adults: int, cabin: str, currency: str) -> List[PriceOffer]:
    token = amadeus_token()
    if not token:
        return []
    base = os.environ.get("AMADEUS_BASE_URL", "https://test.api.amadeus.com")
    params = {
        "originLocationCode": origin,
        "destinationLocationCode": dest,
        "departureDate": departure_date,
        "adults": str(adults),
        "nonStop": "true",
        "currencyCode": currency,
        "max": "250",
    }
    if return_date:
        params["returnDate"] = return_date
    if cabin:
        params["travelClass"] = cabin.upper()
    url = base.rstrip("/") + "/v2/shopping/flight-offers?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode())
    offers: List[PriceOffer] = []
    for item in payload.get("data", []):
        price = item.get("price", {})
        for itin in item.get("itineraries", []):
            segs = itin.get("segments", [])
            if len(segs) != 1:
                continue
            seg = segs[0]
            fn = f"{seg.get('carrierCode', '')}{seg.get('number', '')}"
            fare_detail = {}
            tps = item.get("travelerPricings") or []
            if tps:
                fds = tps[0].get("fareDetailsBySegment") or []
                fare_detail = fds[0] if fds else {}
            offers.append(
                PriceOffer(
                    provider="Amadeus",
                    flight_number=fn,
                    cabin=fare_detail.get("cabin", cabin),
                    booking_class=fare_detail.get("class", ""),
                    fare_basis=fare_detail.get("fareBasis", ""),
                    seats=item.get("numberOfBookableSeats"),
                    price=float(price.get("grandTotal")) if price.get("grandTotal") else None,
                    currency=price.get("currency", currency),
                    raw_match_note="nonStop=true flight-offers API",
                )
            )
    return offers


def fetch_kiwi_prices(origin: str, dest: str, departure_date: str, return_date: str, adults: int, cabin: str, currency: str) -> List[PriceOffer]:
    api_key = os.environ.get("TEQUILA_API_KEY") or os.environ.get("KIWI_TEQUILA_API_KEY")
    if not api_key:
        return []
    cabin_map = {"ECONOMY": "M", "PREMIUM_ECONOMY": "W", "BUSINESS": "C", "FIRST": "F"}
    params = {
        "fly_from": origin,
        "fly_to": dest,
        "date_from": dt.datetime.strptime(departure_date, "%Y-%m-%d").strftime("%d/%m/%Y"),
        "date_to": dt.datetime.strptime(departure_date, "%Y-%m-%d").strftime("%d/%m/%Y"),
        "adults": str(adults),
        "max_stopovers": "0",
        "curr": currency,
        "limit": "200",
    }
    if return_date:
        params["return_from"] = dt.datetime.strptime(return_date, "%Y-%m-%d").strftime("%d/%m/%Y")
        params["return_to"] = dt.datetime.strptime(return_date, "%Y-%m-%d").strftime("%d/%m/%Y")
    if cabin:
        params["selected_cabins"] = cabin_map.get(cabin.upper(), cabin[:1].upper())
    url = "https://api.tequila.kiwi.com/v2/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"apikey": api_key, "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode())
    offers: List[PriceOffer] = []
    for item in payload.get("data", []):
        routes = item.get("route") or []
        if not routes:
            continue
        for seg in routes:
            fn = f"{seg.get('airline', '')}{seg.get('flight_no', '')}"
            offers.append(
                PriceOffer(
                    provider="Kiwi/Tequila",
                    flight_number=fn,
                    cabin=cabin,
                    price=float(item.get("price")) if item.get("price") is not None else None,
                    currency=currency,
                    deep_link=item.get("deep_link", ""),
                    raw_match_note="max_stopovers=0 search API",
                )
            )
    return offers


def attach_prices(records: List[FlightRecord], offers: List[PriceOffer]) -> None:
    by_flight: Dict[str, List[PriceOffer]] = {}
    for offer in offers:
        if offer.flight_number:
            by_flight.setdefault(offer.flight_number.upper().replace(" ", ""), []).append(offer)
    for rec in records:
        keys = {rec.operating_flight.upper().replace(" ", "")}
        keys.update(f.upper().replace(" ", "") for f in rec.marketing_flights)
        matched: List[PriceOffer] = []
        for key in keys:
            matched.extend(by_flight.get(key, []))
        # provider/flight/price de-dupe
        seen = set()
        deduped = []
        for m in matched:
            sig = (m.provider, m.flight_number, m.cabin, m.booking_class, m.price, m.currency)
            if sig not in seen:
                seen.add(sig)
                deduped.append(m)
        rec.prices = deduped
        if deduped:
            providers = sorted({p.provider for p in deduped})
            rec.verification += "; price/cabin matched from " + ", ".join(providers)
            for p in providers:
                rec.sources.append(SourceRecord(p, "API result", "price/cabin provider"))
        else:
            rec.missing.append("price/cabin")


def collect_trip(origin: str, dest: str, departure_date: str, roundtrip: bool, return_date: str, adults: int, cabin: str, currency: str) -> List[FlightRecord]:
    records = fetch_flightstats_direction(origin, dest, departure_date, "outbound")
    if roundtrip:
        if not return_date:
            raise ValueError("--roundtrip requires --return-date")
        records.extend(fetch_flightstats_direction(dest, origin, return_date, "return"))

    offers: List[PriceOffer] = []
    provider_errors = []
    for fetcher in (fetch_amadeus_prices, fetch_kiwi_prices):
        try:
            offers.extend(fetcher(origin, dest, departure_date, return_date if roundtrip else "", adults, cabin, currency))
        except Exception as exc:  # noqa: BLE001
            provider_errors.append(f"{fetcher.__name__}: {exc}")
    attach_prices(records, offers)
    if provider_errors:
        for rec in records:
            rec.sources.append(SourceRecord("price-provider-errors", "", "; ".join(provider_errors[:3])))
    return records


def cabin_label(cabin: str) -> str:
    value = (cabin or "").strip().upper().replace(" ", "_")
    labels = {
        "ECONOMY": "经济舱",
        "PREMIUM_ECONOMY": "豪华经济舱",
        "BUSINESS": "商务舱",
        "FIRST": "头等舱",
    }
    return labels.get(value, cabin or "舱位未明")


def money_label(price: Optional[float], currency: str) -> str:
    if price is None:
        return "价格未明"
    cur = (currency or "").upper()
    symbols = {
        "USD": "US$",
        "HKD": "HK$",
        "CNY": "人民币¥",
        "RMB": "人民币¥",
        "JPY": "JP¥",
        "EUR": "€",
        "GBP": "£",
        "AUD": "A$",
        "CAD": "C$",
        "SGD": "S$",
    }
    symbol = symbols.get(cur, f"{cur} " if cur else "")
    if float(price).is_integer():
        amount = f"{int(price):,}"
    else:
        amount = f"{price:,.2f}"
    return f"{symbol}{amount}"


def terminal_label(terminal: str) -> str:
    terminal = (terminal or "").strip()
    if not terminal:
        return "T?"
    return terminal if terminal.upper().startswith("T") else f"T{terminal}"


def price_offer_label(p: PriceOffer) -> str:
    bits = [cabin_label(p.cabin)]
    if p.provider:
        bits.append(p.provider)
    if p.booking_class:
        bits.append(f"订位舱 {p.booking_class}")
    if p.seats is not None:
        bits.append(f"余位 {p.seats}")
    return f"{money_label(p.price, p.currency)}({', '.join(bits)})"


def render_flight_block(r: FlightRecord) -> List[str]:
    airline = f" ({r.operating_airline})" if r.operating_airline else ""
    shared = " / ".join(r.marketing_flights or [r.operating_flight])
    dep = f"{r.departure_time_local or '??:??'}({r.departure_timezone or '?'}) {r.departure_airport or '?'} {terminal_label(r.departure_terminal)}"
    arr = f"{r.arrival_time_local or '??:??'}({r.arrival_timezone or '?'}) {r.arrival_airport or '?'} {terminal_label(r.arrival_terminal)}"
    aircraft = r.aircraft or (f"机型缺（{r.aircraft_iata}）" if r.aircraft_iata else "机型缺")
    if r.prices:
        price = " / ".join(price_offer_label(p) for p in r.prices)
    else:
        price = "票价: 缺（未配置票价API/平台未返回）"
    return [
        f"{r.operating_flight}{airline}",
        f"共享航班: {shared}",
        f"{dep} → {arr}",
        aircraft,
        price,
    ]


def render_markdown(records: List[FlightRecord], query: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# 直飞航班检索结果")
    lines.append("")
    lines.append(
        f"查询：{query['origin']} → {query['destination']}，出发 {query['departure_date']}，"
        f"往返：{'是' if query.get('roundtrip') else '否'}"
        + (f"，返回 {query.get('return_date')}" if query.get("roundtrip") else "")
    )
    lines.append(f"舱位：{cabin_label(query.get('cabin') or '')}；成人：{query.get('adults')}; 币种：{query.get('currency')}")
    lines.append("范围：仅直飞；共享航班号按同一实际执飞机型分组展示。")
    lines.append("")
    if not records:
        lines.append("未找到直飞航班。")
        return "\n".join(lines)

    for direction in ("outbound", "return"):
        subset = [r for r in records if r.direction == direction]
        if not subset:
            continue
        lines.append(f"## {'去程' if direction == 'outbound' else '返程'}")
        lines.append("")
        for i, r in enumerate(subset):
            if i:
                lines.append("")
            lines.extend(render_flight_block(r))
        lines.append("")

    missing_notes = []
    if any(not r.prices for r in records):
        missing_notes.append("部分/全部航班缺票价：未配置票价API或平台未返回可匹配报价；不要臆测 OTA 价格。")
    if any(not r.aircraft_age for r in records):
        missing_notes.append("机龄未展示：公开航班计划页未返回机尾号/注册号，不能可靠计算。")
    if missing_notes:
        lines.append("## 缺漏说明")
        for note in missing_notes:
            lines.append(f"- {note}")
        lines.append("")

    lines.append("## 原始来源")
    seen = set()
    for r in records:
        for s in r.sources:
            sig = (s.name, s.url, s.note)
            if sig in seen:
                continue
            seen.add(sig)
            if s.url:
                lines.append(f"- {r.operating_flight} {s.name}: {s.url}" + (f" ({s.note})" if s.note else ""))
            elif s.note:
                lines.append(f"- {r.operating_flight} {s.name}: {s.note}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Find direct flights and optional cabin/price offers.")
    parser.add_argument("--origin", required=True, help="Origin IATA airport code, e.g. CAN")
    parser.add_argument("--destination", required=True, help="Destination IATA airport code, e.g. HND")
    parser.add_argument("--departure-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--roundtrip", action="store_true", help="Search return flights too")
    parser.add_argument("--return-date", default="", help="YYYY-MM-DD; required with --roundtrip")
    parser.add_argument("--adults", type=int, default=1)
    parser.add_argument("--cabin", default="ECONOMY", help="ECONOMY, PREMIUM_ECONOMY, BUSINESS, FIRST")
    parser.add_argument("--currency", default="CNY")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown")
    args = parser.parse_args(argv)

    origin = normalize_iata(args.origin)
    dest = normalize_iata(args.destination)
    # Validate date format.
    dt.date.fromisoformat(args.departure_date)
    if args.return_date:
        dt.date.fromisoformat(args.return_date)

    records = collect_trip(
        origin=origin,
        dest=dest,
        departure_date=args.departure_date,
        roundtrip=args.roundtrip,
        return_date=args.return_date,
        adults=args.adults,
        cabin=args.cabin,
        currency=args.currency.upper(),
    )
    query = vars(args) | {"origin": origin, "destination": dest}
    if args.json:
        print(json.dumps({"query": query, "records": [asdict(r) for r in records]}, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(records, query))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        print(f"HTTP error: {exc.code} {exc.reason} while fetching {exc.url}", file=sys.stderr)
        raise SystemExit(2)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
