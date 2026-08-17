# FairDeal

Point FairDeal at a rent listing, lease, college/major choice, or freelance contract — get an honest "is this fair, and why" verdict against real benchmark data.

One core engine (`fairdeal/engine.py`): extract a claim → compare it to a benchmark → output a verdict. Four pluggable modules share it:

| Module | Input | Benchmark data | Status |
|---|---|---|---|
| Rent check | chat criteria (location/university/budget) or a listed rent | HUD Fair Market Rent + BLS regional CPI | day-1 vertical slice |
| Lease review | scanned lease PDF | red-flag clause + escalation-term library | not started |
| College ROI | major + school choice | IPEDS cost/outcomes data | not started |
| Contract review | freelance/consulting contract PDF | red-flag clause library | not started |

Local-first: extraction runs through [llm-ladder](../llm-ladder)'s confidence-gated cascade (local models first, escalate only on low confidence). Nothing leaves the machine unless a paid API tier is configured in `chains.yaml`.

## Endpoint verification log (day 1)

Recorded here as each external data source is confirmed live — see `tests/fixtures/` for saved responses.

- **Craigslist RSS / HTML search** — DEAD. Both `?format=rss` and the plain HTML search page return HTTP 403 "blocked" (bot-detection). Confirmed 2026-08-16. No working zero-key path to individual rental listings was found (Zillow and Apartments.com also 403 direct-fetch; DuckDuckGo HTML search works but only surfaces category/landing pages, not individual listings). **Default search provider ships as a labeled seed/demo dataset** (`fairdeal/craigslist.py`) instead. To get real listings, register a paid provider (e.g. RentCast) and add it behind `fairdeal/search.py`'s `SearchProvider` interface.
- **HUD Fair Market Rent API** — live, requires a free bearer token. Unauthenticated request confirmed `401 {"error":"Unauthenticated"}` (fixture: `tests/fixtures/hud_fmr_unauth_response.json`). **Action needed from Parth**: register at https://www.huduser.gov/hudapi/public/register.html and set `HUD_API_TOKEN`. Until then, `fairdeal/hud.py` falls back to a small static FMR reference table.
- **BLS CPI v2** — live, works with no key at low volume. Confirmed 2026-08-16 (fixture: `tests/fixtures/bls_cpi_sf.json`).
- **Nominatim geocoding/reverse-geocoding** — live, no key, rate-limited to 1 req/sec (throttled in `fairdeal/geocode.py`). Confirmed for both search and reverse (fixtures: `tests/fixtures/nominatim_search_usf.json`, `tests/fixtures/nominatim_reverse_sf.json`).
- **IPEDS bulk data** (module 3, deferred) — not yet checked; do this before starting module 3.

## Environment variables

- `HUD_API_TOKEN` — optional. Free token from huduser.gov. Falls back to a static FMR table when unset.
- `FAIRDEAL_SEARCH_PROVIDER` — optional, defaults to `seed`. Set to a registered provider name once a real listings API is wired in.

## API contract (frozen for day-1 frontend work)

`POST /api/rentcheck` body `{"message": "<free text rental request>"}` → `200 OK`:

```json
{
  "reply_text": "Found 3 places near your criteria, 2 look fairly priced.",
  "data_source": "seed-demo",
  "results": [
    {
      "title": "Sunny 1BR in the Inner Sunset",
      "price": 2400,
      "url": "https://example.com/seed-listing/1",
      "distance_miles": 1.4,
      "rating": "borderline",
      "delta": 1.12,
      "explanation": "2,400 is 1.12x the FMR 1BR San Francisco (2,149, HUD FMR 2024 (static fallback, no HUD_API_TOKEN configured)) — borderline."
    }
  ]
}
```

`rating` is one of `fair` / `borderline` / `unfair` / `unknown`. `delta` may be `null` (rating `unknown`). `data_source` names the active search provider and is present on every `200` response, including empty ones — the default `"seed-demo"` means the listings are the demo dataset, not live rentals; clients should surface it. Errors: `400` malformed request, `503` local model cascade unavailable (`{"error": "..."}"`), `500` unexpected.

## Run

```
source .venv/bin/activate
python -m fairdeal.server
```

Open `http://localhost:8000`.
