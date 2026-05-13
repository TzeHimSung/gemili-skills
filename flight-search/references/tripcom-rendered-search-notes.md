# Trip.com Rendered Search Notes

Use these notes when a user asks for OTA fare verification in addition to schedule truth.

## Airport-specific Tokyo searches

Trip.com may not expose a stable airport-pair landing URL for every route. Example observed during HKG → HND work:

- `https://www.trip.com/flights/hong-kong-to-tokyo/airfares-hkg-hnd/...` returned a Trip.com 404 page.
- The broader city-pair page `HKG → TYO` rendered normally.
- Correct workflow: open the city-pair search, enable `Nonstop`, then apply `Arrival Airport = HND / Haneda Airport` in the rendered filters before reading any fares.

Do not attach city-level `TYO` headline prices to Haneda-specific rows unless the result list itself visibly shows `HND` on the flight row.

## Browser extraction pattern

After the Trip.com results render, browser console extraction can reliably expose the visible rows:

```js
[...document.querySelectorAll('.result-item.J_FlightItem, .result-item')]
  .map(e => e.innerText)
  .filter(t => t.includes('HND'))
```

Also capture the page's own update timestamp:

```js
document.body.innerText.match(/\*Last updated: [0-9:]+/)?.[0]
```

Use these only as evidence for currently visible rendered results. Prices remain volatile until the final booking page.

## Cross-check behavior seen on HKG → HND

On 2026-05-14 HKG → HND, Trip.com rendered some operating flights and some codeshares as separate sales rows. A single physical flight can have multiple prices depending on marketing carrier; preserve source labels rather than collapsing prices silently.

Example: CX542 appeared as Cathay Pacific and as Japan Airlines operated by Cathay Pacific, with different visible prices. FlightStats should remain the authority for the operating-flight grouping; Trip.com should be treated as a shopping/fare source.

## Reporting rule

If schedule source has a flight but Trip.com does not render a corresponding fare row, report `Trip.com fare not visible` rather than assuming sold out or unavailable. If Trip.com renders a fare without a visible flight number, match cautiously by airline, local times, airports, terminals, duration, and nonstop status, and label it as a visible OTA match rather than API-confirmed fare matching.
