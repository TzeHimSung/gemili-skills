---
name: flight-search
description: Use when the user gives origin, destination, departure date, one-way/round-trip flag, optional return date, and asks for flight options with airports, terminals, departure/arrival times, aircraft type/age, cabin and prices, with cross-source verification. Current implementation supports non-stop flights first and is designed to evolve to connections later.
version: 1.0.2
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [aviation, flights, airfare, travel, scraping]
    related_skills: [aviation-tracking]
---

# Flight Search

## Overview

Use this skill to answer itinerary-style flight-search requests where the user supplies:

- 出发地 / origin: preferably a 3-letter IATA airport code such as `CAN`.
- 目的地 / destination: preferably a 3-letter IATA airport code such as `HND`.
- 出发日期 / departure date: `YYYY-MM-DD`.
- 是否往返 / round trip flag.
- 返回日期 / return date when round trip.
- Optional cabin, adult count, currency.

The goal is to find **all direct / non-stop flights only** and report: actual operating flight, marketing/codeshare flight numbers, airports, terminals, departure/arrival times with time zones, aircraft type, aircraft age if a reliable tail/registration is available, cabin and price if shopping APIs return it, and source links.

The included script fixes the repeatable part in code:

```bash
python3 ~/.hermes/skills/research/flight-search/scripts/flight_search.py \
  --origin CAN --destination HND --departure-date 2026-05-14 \
  --cabin ECONOMY --currency CNY
```

Round trip:

```bash
python3 ~/.hermes/skills/research/flight-search/scripts/flight_search.py \
  --origin CAN --destination HND --departure-date 2026-05-14 \
  --roundtrip --return-date 2026-05-20 \
  --cabin ECONOMY --currency CNY
```

JSON for post-processing:

```bash
python3 ~/.hermes/skills/research/flight-search/scripts/flight_search.py \
  --origin CAN --destination HND --departure-date 2026-05-14 --json
```

## When to Use

Use this skill when:

- User asks for flights between two cities/airports on a date.
- User specifically asks for 直飞 / non-stop / direct flights.
- User wants a table with terminals, times, aircraft, cabin, price, and source links.
- User asks whether OTA platforms such as 携程/Trip.com/飞猪 agree with another source.

Do not use this skill for:

- Real-time aircraft position tracking after departure; use `aviation-tracking`.
- Multi-city or connecting itineraries; this skill intentionally filters to non-stop only.
- Hidden-city ticketing, fare-rule abuse, scraping bypass, captcha bypass, or account automation.

## Data Source Strategy

### Schedule and status source: FlightStats / Cirium public pages

The script queries FlightStats/Cirium `api-next` JSON endpoints for rolling route windows and parses public page JSON as a fallback. Then it fetches each flight detail API/page to supplement:

- actual operating flight number,
- codeshare / marketing flight numbers,
- airport names and IATA codes,
- departure/arrival terminals when present,
- scheduled local times and time-zone labels,
- flight status and on-time description,
- aircraft type / IATA aircraft code,
- duration,
- original route/detail URLs.

This source is good for schedule truth and codeshare grouping. It is not a full shopping engine.

### Price/cabin sources: API-first, not captcha bypass

OTA sites such as Trip.com/携程/飞猪 often return challenge-validation pages or require browser/device fingerprints. Do **not** claim their prices unless you actually saw the result. Do **not** try to bypass captcha or anti-bot checks.

The fixed script supports these optional API providers:

1. **Amadeus Flight Offers**
   - Env vars: `AMADEUS_CLIENT_ID`, `AMADEUS_CLIENT_SECRET`.
   - Optional env: `AMADEUS_BASE_URL`; defaults to `https://test.api.amadeus.com`.
   - Uses `nonStop=true` and maps cabin/booking class/fare basis when returned.

2. **Kiwi / Tequila**
   - Env vars: `TEQUILA_API_KEY` or `KIWI_TEQUILA_API_KEY`.
   - Uses `max_stopovers=0`.
   - Returns price/deep link when available.

If no price provider credentials are configured, the script still returns schedule data and explicitly marks `price/cabin` as missing. That is preferable to inventing prices.

## Required Workflow

1. **Normalize the user input.**
   - Convert city names to IATA airport codes if needed. For ambiguous cities (Tokyo has HND/NRT; Osaka has KIX/ITM/UKB), ask only if the user did not specify the airport.
   - Use the exact target airport if the user names it, e.g. “东京羽田机场” -> `HND`.
   - Confirm date as `YYYY-MM-DD`; include weekday and time zones in the final answer.

2. **Run the fixed script.**
   - One-way:
     ```bash
     python3 ~/.hermes/skills/research/flight-search/scripts/flight_search.py \
       --origin <ORI> --destination <DST> --departure-date <YYYY-MM-DD> \
       --cabin <ECONOMY|PREMIUM_ECONOMY|BUSINESS|FIRST> --currency <CURRENCY>
     ```
   - Round trip:
     ```bash
     python3 ~/.hermes/skills/research/flight-search/scripts/flight_search.py \
       --origin <ORI> --destination <DST> --departure-date <YYYY-MM-DD> \
       --roundtrip --return-date <YYYY-MM-DD> \
       --cabin <ECONOMY|PREMIUM_ECONOMY|BUSINESS|FIRST> --currency <CURRENCY>
     ```

3. **If credentials exist, cross-check prices/cabins.**
   - The script automatically attaches Amadeus/Kiwi offers by matching operating and marketing flight numbers.
   - Treat prices as source-specific and time-sensitive.
   - If two providers disagree, list both instead of averaging or choosing silently.

4. **If the user asks for OTA-specific verification, use browser manually only when necessary.**
   - Try normal browsing/search pages.
   - Trip.com airport-pair URLs may 404 for specific airport destinations such as `hkg-hnd`; use the broader city-pair page (for example `hkg-tyo`) with `nonstoponly=on`, then apply the arrival-airport filter (`HND`) in the rendered page.
   - If the page returns challenge/captcha, say so clearly and do not present the OTA as verified.
   - If a browser-rendered OTA result is visible, record screenshot/URL/time and compare flight number + date + local departure/arrival times against the script output.

5. **Produce the final table in the conversation, not just a file path.**
   - User prefers direct report content in-chat.
   - Include original links for every flight or source group.
   - State whether “all flights” means actual operating flights or marketing/codeshare flight numbers.

## Interpretation Rules

### Actual flights vs. marketing/codeshare flights

A single aircraft movement can be sold under multiple flight numbers. Always distinguish:

- **Actual operating flight**: the airline/flight that operates the aircraft.
- **Marketing/codeshare flight**: alternate sales flight numbers attached to the same physical flight.

Report both counts when useful:

```text
实际执飞直飞航班：4 班
按销售航班号展开：12 个航班号
```

### Aircraft age / 机龄

Never infer aircraft age from aircraft type. `Boeing 787-8` is not enough to determine age.

Fill aircraft age only if a reliable source provides a registration/tail number and that registration is matched to fleet data. Public schedule pages usually do not expose future-day tail assignments. If missing, write:

```text
机龄：缺；公开航班计划页未返回机尾号/注册号，不能可靠计算。
```

### Cabin and price

Cabin/price must come from a shopping source, not a schedule source.

- If Amadeus/Kiwi returns fare detail: show provider, cabin, booking class, fare basis, bookable seats, price, currency.
- If an OTA page is manually visible: show platform and timestamp.
- If no provider returns it: mark as missing and explain which credentials or manual check would be needed.

### Time zones

Always print dates/time zones explicitly:

- China: local times may be labeled `CST` by FlightStats (China Standard Time, UTC+8).
- Japan: `JST` (UTC+9).
- Do not convert away the local airport time unless the user asks. Local airport time is the most useful for travel.

## Cross-Verification Standard

For each flight row, set a verification note:

- `FlightStats schedule/detail matched`: schedule and detail pages agree.
- `price/cabin matched from Amadeus`: the flight number was matched to an offer.
- `price/cabin matched from Kiwi/Tequila`: the flight number was matched to an offer.
- `single-source schedule`: only schedule was available.
- `OTA visible manually`: only if the browser rendered the OTA result without challenge and you inspected it.

When two sources disagree:

1. Trust airline/airport/schedule sources for flight existence, times, terminals, aircraft type.
2. Trust shopping APIs/OTAs only for fare availability and price.
3. Show both values with source labels and timestamp rather than silently merging.
4. If the difference is material (different departure time, airport, direct vs. connection), flag the row as `needs manual verification`.

## Output Format

Default final answer should use compact, itinerary-style blocks rather than a wide Markdown table. Keep one blank line between flight blocks. The per-flight block must follow this shape:

```text
<operating flight> (<operating airline>)
共享航班: <operating/marketing flight> / <codeshare> / ...
<HH:MM>(<dep timezone>) <DEP> T<terminal> → <HH:MM>(<arr timezone>) <ARR> T<terminal>
<aircraft type>
<price>(<cabin in Chinese>, <provider>)
```

Example:

```text
CX548 (Cathay Pacific)
共享航班: CX548 / FJ5452 / JL7030 / QR5820
08:40(HKT) HKG T1 → 13:55(JST) HND T3
Boeing 777-300ER
人民币¥8,650(经济舱, Trip.com)
```

Additional rules:

- If price is missing, use `票价: 缺（未配置票价API/平台未返回）` on the fifth line; do not hallucinate OTA prices.
- If several price providers return offers, join offer strings on one line with ` / ` and keep provider names inside parentheses.
- Default fare display should be RMB/CNY. The script default is `--currency CNY`; when a fare source supports currency selection, request CNY and render it as `人民币¥1,234`.
- If an OTA/source only visibly returns a non-RMB price, do not silently convert with an unstated FX rate; either switch the source UI/API to CNY or label the original currency explicitly.
- Still include a short header with query/range and a trailing `原始来源` section so every flight/source remains traceable.
- Keep time labels attached to the local scheduled time as `<HH:MM>(<TZ>)`, e.g. `08:40(HKT)` and `13:55(JST)`.
- Display terminals as `T1`, `T3`, or `T?` when absent.

Skeleton:

```text
# 直飞航班检索结果

查询：<origin> → <destination>，出发 <YYYY-MM-DD>，往返：<是/否>
舱位：<中文舱位>；成人：<N>; 币种：<CURRENCY>
范围：仅直飞；共享航班号按同一实际执飞机型分组展示。

## 去程

CX548 (Cathay Pacific)
共享航班: CX548 / FJ5452 / JL7030 / QR5820
08:40(HKT) HKG T1 → 13:55(JST) HND T3
Boeing 777-300ER
人民币¥8,650(经济舱, Trip.com)

## 缺漏说明
- ...

## 原始来源
- CX548 FlightStats detail: ...
```

## Maintenance Notes

Script path:

```text
~/.hermes/skills/research/flight-search/scripts/flight_search.py
```

Session/provider notes:

```text
~/.hermes/skills/research/flight-search/references/data-source-notes.md
~/.hermes/skills/research/flight-search/references/tripcom-rendered-search-notes.md
```

Use the reference files for FlightStats/Cirium endpoint behavior, OTA anti-bot caveats, supported fare API environment variables, Trip.com rendered-search quirks such as city-pair search plus airport filtering, and the smoke-test routes used when this skill was created.

The script uses only Python standard library so it works in a fresh Hermes environment. It avoids Playwright/Selenium as the default because OTA pages are anti-bot sensitive and brittle.

When improving this skill, prefer adding a provider module/function to the script rather than hard-coding one-off scraping in the answer. Provider functions should return normalized `PriceOffer` objects and must record provider/source names.

## Common Pitfalls

1. **Treating codeshares as separate aircraft.** Group by `flightId` / same departure-arrival times and show marketing flight numbers separately.
2. **Hallucinating price.** FlightStats does not provide live fare price. Mark price missing unless a shopping source returned it.
3. **Hallucinating aircraft age.** Aircraft type is not aircraft age. Need registration/tail number first.
4. **Ignoring time zones.** Always label departure and arrival local time zones.
5. **Claiming OTA verification after a challenge page.** A challenge/captcha page is not a search result.
6. **Using city-level OTA prices as airport-specific fares.** Trip.com city pages such as `HKG → TYO` may show aggregate Tokyo fares and slogans like “from US$…”. Do not attach those prices to `HND` rows unless the rendered result/booking path visibly confirms Haneda, date, flight number, and nonstop status.
7. **Using city code when user specified an airport.** If user says 羽田, use `HND`, not Tokyo all-airport `TYO`.
8. **Not checking return direction.** Round trip requires a second search with origin/destination reversed.

## Verification Checklist

- [ ] Input date(s) parsed as `YYYY-MM-DD`; weekday/time zone stated in final report.
- [ ] Origin/destination are IATA codes and reflect the user's airport intent.
- [ ] Script run completed without fatal errors.
- [ ] Rows are limited to non-stop flights.
- [ ] Actual operating flights are separated from marketing/codeshare flight numbers.
- [ ] Terminals/times/aircraft/status have source links.
- [ ] Cabin/price are either source-backed or explicitly marked missing.
- [ ] Aircraft age is either source-backed via registration or explicitly marked missing.
- [ ] All original links used are included in the response.
