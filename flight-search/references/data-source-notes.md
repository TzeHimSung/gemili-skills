# Flight Search Data Source Notes

Session-derived provider notes for future maintenance of `flight-search`.

## FlightStats / Cirium

- Prefer public `api-next` JSON endpoints over HTML scraping for schedule truth.
- Use route/date windows first, then fetch detail pages/API for each flight to fill terminal, aircraft, status, and codeshare/marketing numbers.
- Detail pages can sometimes return a lightweight/legacy shell or omit embedded data. The script should retry alternate detail URLs, including variants with/without `flightId`, and keep the schedule row instead of dropping the flight.
- FlightStats is suitable for flight existence, operating carrier/flight, times, terminals, aircraft type, status, and codeshare grouping. It is not a fare source.

## OTA / Shopping Sources

- Trip.com/携程/飞猪-style OTA pages can return challenge validation or require browser/device fingerprints. Do not describe an OTA as verified unless an actual search result was visible and inspected.
- Do not bypass CAPTCHA, account, or anti-bot controls. Use API-first providers for fares.
- Supported script env vars for fares:
  - `AMADEUS_CLIENT_ID`, `AMADEUS_CLIENT_SECRET`, optional `AMADEUS_BASE_URL`.
  - `TEQUILA_API_KEY` or `KIWI_TEQUILA_API_KEY`.
- Prices are time-sensitive and provider-specific. If providers disagree, preserve source labels rather than averaging.

## Validation Example

Known smoke-test route/date used during creation:

```bash
python3 ~/.hermes/skills/research/flight-search/scripts/flight_search.py \
  --origin CAN --destination HND --departure-date 2026-05-14 --currency CNY
```

Expected actual non-stop operating flights for that test date were:

- CZ385
- JL88
- NH924
- CZ3085

Use this as a rough regression smoke test for schedule extraction, not as current travel advice.

## Reporting Rule

When the script lacks fare credentials or aircraft registration/tail data, explicitly mark price/cabin or aircraft age as missing. Never infer price from schedule data or age from aircraft type.
