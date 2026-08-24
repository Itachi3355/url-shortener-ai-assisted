# URL Shortener — AI-Assisted Engineering

A URL shortener with core APIs, click analytics, and abuse controls, built as a
demonstration of AI-assisted engineering execution. The engineering process —
requirement normalization, decomposition, AI usage discipline, and validation —
is documented in [SCENARIOS.md](SCENARIOS.md) and [AI-USAGE.md](AI-USAGE.md);
design decisions in [ARCHITECTURE.md](ARCHITECTURE.md).

## Setup

Requires Python 3.11+.

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open **http://127.0.0.1:8000** — the LinkDesk console. Raw OpenAPI docs are
at [/docs](http://127.0.0.1:8000/docs).

## The console

`GET /` serves a single static page (no build step, no framework) that exercises
every endpoint against the live server:

- **Create a short link** — destination, optional alias, optional TTL. On success
  it shows the short URL, a scannable QR code, and copy / open actions.
- **Your links** — every link with live click counts. *Stats* expands under that
  row with a 7-day click chart and referrer breakdown; click again to collapse.
- **Guided checks** — seven one-click probes. Each names the status code it
  expects *before* it runs, then shows PASS/FAIL plus the raw response body.
  They assert the same things the pytest suite does, so a reviewer can confirm
  behavior without reading the test file.

| Check | Expects | What it proves |
|---|---|---|
| Create a link | `201` | Valid URL accepted, 7-char code issued |
| Redirect works | `307` | Forwards to destination without permanent caching |
| Duplicate alias rejected | `409` | Second claim conflicts instead of overwriting |
| `javascript:` URL blocked | `422` | Scheme allowlist blocks script payloads |
| Private IP target blocked | `422` | Won't mask links into internal infrastructure |
| Unknown code is 404 | `404` | No broken redirects for missing/expired links |
| Rate limit engages | `429` | One create past the configured limit is throttled |

## Quick demo (CLI equivalent)

```bash
curl -s -X POST http://127.0.0.1:8000/api/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.schwab.com/careers", "alias": "careers"}'
```

```bash
curl -i http://127.0.0.1:8000/careers
```

```bash
curl -s http://127.0.0.1:8000/api/links/careers/stats
```

On Windows PowerShell use `curl.exe` (bare `curl` is an alias for
`Invoke-WebRequest` and won't accept these flags).

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/shorten` | Create link. Body: `url`, optional `alias` (4–32 chars), optional `ttl_days` (1–365) |
| GET | `/{code}` | 307 redirect; records click. 404 if unknown/expired |
| GET | `/api/links` | All links with click counts, newest first |
| GET | `/api/links/{code}/stats` | Total clicks, 7-day daily series, top referrers |
| GET | `/api/links/{code}/qr` | QR code for the short link, as SVG |
| DELETE | `/api/links/{code}` | Remove link (clicks cascade) |
| GET | `/health` | Liveness + DB check |
| GET | `/` | LinkDesk console (static page) |

Errors: `422` invalid URL/alias, `409` alias taken, `429` rate limited
(10 creates/min/IP), `404` unknown or expired.

A `429` carries a `Retry-After` header saying how many seconds until the next
request is allowed, per RFC 6585. The console reads it and counts down rather
than guessing.

### Hitting the rate limit while demoing

Expected — the **Rate limit engages** check deliberately spends the whole
minute's budget, so link creation is blocked for ~60s afterwards. Run it last.
To clear it immediately, restart the server (the limiter is in-memory), or give
the demo more headroom. Above 25/min the check reports SKIPPED rather than
running a long burst that would bury the link table:

```bash
RATE_LIMIT_PER_MIN=100 uvicorn app.main:app --reload
```

On PowerShell: `$env:RATE_LIMIT_PER_MIN=100; uvicorn app.main:app --reload`

Every response carries an `X-Request-ID` header. Supply your own to trace a
request end to end; otherwise one is generated.

## Observability

Requests are logged as one JSON object per line, correlated by request ID:

```json
{"ts": "2026-08-20T15:51:10", "level": "INFO", "request_id": "demo-trace-1",
 "message": "request", "method": "GET", "path": "/health", "status": 200, "duration_ms": 5.67}
```

Structured rather than formatted, so a log aggregator can index `status` and
`duration_ms` without parsing prose. An incoming `X-Request-ID` is honored so an
upstream trace ID survives into these logs.

## Tests

```bash
python -m pytest tests/ -q
```

28 tests: happy paths, alias collisions, invalid inputs, expiry, delete cascade,
rate-limit window behavior and `Retry-After`, private-IP rejection, QR
generation, request-ID propagation, and the error-body contract the console
depends on. Each test runs against a fresh temp database.

```bash
python -m ruff check app tests
```

Both gates run on every push via [GitHub Actions](.github/workflows/ci.yml) —
the quality gates are enforced by CI, not just claimed in a document.

## Testing approach

- **API-level tests through `TestClient`** rather than unit tests per function —
  they exercise routing, validation, persistence, and status codes together,
  which is where shortener bugs actually live.
- **Direct unit tests only where time matters** (`test_rate_limit_window_slides`
  injects clock values instead of sleeping).
- **State isolation**: temp DB per test via fixture; rate-limiter reset per test.

## Limitations and trade-offs (deliberate, for prototype scope)

- **SQLite, single process** — no horizontal scaling. Path to production:
  Postgres + Redis for the rate limiter and hot-code cache.
- **In-memory rate limiter** — resets on restart, per-process only. Marked in
  code with the upgrade path.
- **Synchronous click insert on the redirect path** — adds ~1ms; queue/batch if
  redirect latency ever matters.
- **No auth** — anyone can create/delete links. Real deployment needs API keys
  on the management endpoints.
- **DNS-based SSRF gap**: the private-IP guard checks literal IPs, not domains
  that *resolve* to private IPs. Resolving at creation time still allows
  DNS rebinding; a real fix validates at a fetch proxy, out of scope here.
- **No pagination on stats or link list** — referrers capped at 10, links at 50.
- **Console has no auth and lists every link** — it is a demo surface for a
  single-tenant prototype, not a customer-facing dashboard. With auth added,
  `/api/links` would filter by owner.
- **Logs go to stdout only** — correct for a container, but there is no shipping
  or retention configured.
