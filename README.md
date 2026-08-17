# FairDeal

Point FairDeal at a rent listing, lease, college/major choice, or freelance contract — get an honest "is this fair, and why" verdict against real benchmark data.

One core engine (`fairdeal/engine.py`): extract a claim → compare it to a benchmark → output a verdict. Four pluggable modules share it:

| Module | Input | Benchmark data | Status |
|---|---|---|---|
| Rent check | chat criteria (location/university/budget) or a listed rent | HUD Fair Market Rent + BLS regional CPI | built |
| Lease review | pasted lease text | 7-entry red-flag clause + escalation-term library (`fairdeal/clauses.py`) | built |
| College ROI | school name + optional major | College Scorecard (IPEDS-derived) cost/earnings data | built |
| Contract review | pasted contract text | 7-entry red-flag clause library (`fairdeal/clauses.py`) | built |

Lease/contract review are deliberately independent of the local-LLM cascade — deterministic keyword matching against the clause library, so they keep working even when Ollama is down (unlike rent-check's chat parsing). Both accept a pasted-text OR an uploaded PDF (`fairdeal/ocr.py`: pypdf text layer + tesseract fallback for scanned pages). Rent Check has a model selector in the UI — pick any Ollama-pulled model for that one request via `GET /api/models` / the `model` field on `POST /api/rentcheck`, bypassing `chains.yaml`'s configured cascade.

Local-first: extraction runs through [llm-ladder](../llm-ladder)'s confidence-gated cascade (local models first, escalate only on low confidence). Nothing leaves the machine unless a paid API tier is configured in `chains.yaml`.

## Endpoint verification log (day 1)

Recorded here as each external data source is confirmed live — see `tests/fixtures/` for saved responses.

- **Craigslist RSS / HTML search** — DEAD. Both `?format=rss` and the plain HTML search page return HTTP 403 "blocked" (bot-detection). Confirmed 2026-08-16. No working zero-key path to individual rental listings was found (Zillow and Apartments.com also 403 direct-fetch; DuckDuckGo HTML search works but only surfaces category/landing pages, not individual listings). **Default search provider ships as a labeled seed/demo dataset** (`fairdeal/craigslist.py`) instead. To get real listings, register a paid provider (e.g. RentCast) and add it behind `fairdeal/search.py`'s `SearchProvider` interface.
- **HUD Fair Market Rent API** — live, requires a free bearer token. Unauthenticated request confirmed `401 {"error":"Unauthenticated"}` (fixture: `tests/fixtures/hud_fmr_unauth_response.json`). **Action needed from Parth**: register at https://www.huduser.gov/hudapi/public/register.html and set `HUD_API_TOKEN`. Until then, `fairdeal/hud.py` falls back to a small static FMR reference table.
- **BLS CPI v2** — live, works with no key at low volume. Confirmed 2026-08-16 (fixture: `tests/fixtures/bls_cpi_sf.json`).
- **Nominatim geocoding/reverse-geocoding** — live, no key, rate-limited to 1 req/sec (throttled in `fairdeal/geocode.py`). Confirmed for both search and reverse (fixtures: `tests/fixtures/nominatim_search_usf.json`, `tests/fixtures/nominatim_reverse_sf.json`).
- **DuckDuckGo HTML search** (rent-check's `web_references`) — live, no key. Requires POST (a GET just returns the empty search shell) and a browser-like User-Agent. Ad results always redirect through `duckduckgo.com/y.js` — filtered out in `fairdeal/websearch.py`, only organic direct-domain links are kept.
- **Ollama** — the local model runtime itself needs a real model pulled and reachable at `:11434`. `chains.yaml`'s tiers must be actual `ollama pull`-able tags; `qwen2.5:3b` (small, fast) is pulled by default. If `~/.ollama/models` symlinks to external/offline storage, either reconnect it or run `OLLAMA_MODELS=<a real local path> ollama serve` and re-pull.
- **College Scorecard API** (college ROI) — live, works with the public `DEMO_KEY`, no registration required (a free personal key raises the rate limit — set `SCORECARD_API_KEY`). Confirmed 2026-08-16 (fixture: `tests/fixtures/scorecard_usf.json`). **Real gotcha found while integrating**: the API's `fields=` narrow-selection parameter silently returns `null` for every nested `*.consumer.*` field (net price, earnings) even though those same fields resolve correctly in the full unfiltered response — `fairdeal/scorecard.py` always fetches the full response and parses client-side because of this. Also: Scorecard's relevance ranking does NOT put an exact school-name match first (searching "University of San Francisco" ranks a different school, UC-San Francisco, above the exact match) — `find_school()` prefers an exact case-insensitive match over API result order.

## Environment variables

- `HUD_API_TOKEN` — optional. Free token from huduser.gov. Falls back to a static FMR table when unset.
- `FAIRDEAL_SEARCH_PROVIDER` — optional, defaults to `seed`. Set to a registered provider name once a real listings API is wired in.
- `SCORECARD_API_KEY` — optional. Free key from api.data.gov/signup. Falls back to the shared `DEMO_KEY` (lower rate limit) when unset.

## API contracts

`GET /api/models` → `{"models": ["qwen2.5:3b", ...]}` — Ollama-pulled model tags for the UI's model selector. Degrades to `{"models": []}` if Ollama isn't reachable.

`POST /api/rentcheck` body `{"message": "<free text rental request>", "model": "<optional Ollama tag>"}` → `200 OK`. `model` overrides `chains.yaml`'s configured cascade with a single-tier, single-sample chain for that exact model — omit (or blank) to use the configured cascade as normal.

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
  ],
  "web_references": [
    {"title": "Apartments For Rent in San Francisco CA - Zillow", "url": "https://www.zillow.com/san-francisco-ca/apartments/"}
  ]
}
```

`web_references` is a best-effort supplement — real live DuckDuckGo search results (`fairdeal/websearch.py`) for the query, e.g. real Zillow/Apartments.com category-search pages for the area. These are NOT individually priced listings (that data is bot-blocked, see the endpoint verification log) and are never run through the fairness-verdict engine — they're unverified reference links, always shown separately from `results`. Degrades to `[]` on search failure or when no anchors were mentioned.

`POST /api/leasereview` / `POST /api/contractreview` body `{"document_text": "<pasted text>"}` OR `{"pdf_base64": "<base64-encoded PDF>"}` (the latter is OCR'd server-side via `fairdeal/ocr.py`; `pdf_base64` takes priority if both are somehow sent) → `200 OK`:

```json
{
  "reply_text": "Found 2 red flags out of 2 clauses discussed; 5 topics not addressed at all.",
  "data_source": "clause-library-v1",
  "results": [
    {"title": "Security Deposit Clause", "rating": "unfair", "delta": null, "explanation": "..."}
  ]
}
```

Ranked worst-first (unfair → borderline → unknown → fair) — the scariest findings surface immediately, opposite of rent-check's best-first order. `unknown` means the topic was never mentioned in the document, not that it's fine — silence on a high-severity topic (e.g. liability) ranks above silence on a low-severity one.

`POST /api/collegeroi` body `{"school": "<school name>", "major": "<optional>"}` → `200 OK`:

```json
{
  "reply_text": "University of San Francisco: borderline ROI — 4-year cost is 1.4x typical 10-year earnings.",
  "data_source": "college-scorecard",
  "results": [
    {"title": "University of San Francisco", "rating": "borderline", "delta": 1.41, "explanation": "...", "completion_rate_4yr": 0.7006}
  ]
}
```

ROI is calculated at the school level (4-year net cost vs 10-year median earnings, fair ≤1.0x, borderline ≤2.5x — a disclosed heuristic, not an official benchmark, same honesty standard as rent-check's HUD FMR caveat); `major` is disclosed in the explanation but doesn't change the math, since Scorecard's per-major earnings data is too sparse to be reliable.

All four: `rating` is one of `fair` / `borderline` / `unfair` / `unknown`. `delta` may be `null`. `data_source` is present on every `200`, including empty ones. Errors: `400` malformed request, `503` local model cascade unavailable (rent-check only — the other three modules don't depend on Ollama), `500` unexpected.

## Run

```
source .venv/bin/activate
python -m fairdeal.server
```

Open `http://localhost:8000`.
