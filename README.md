# URL Shortener — AI-Assisted Engineering Assignment

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

Interactive API docs: http://127.0.0.1:8000/docs

## Quick demo

```bash
# create a short link
curl -s -X POST http://127.0.0.1:8000/api/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.schwab.com/careers", "alias": "schwab"}'

# follow it (307 → target)
curl -i http://127.0.0.1:8000/schwab

# stats
curl -s http://127.0.0.1:8000/api/links/schwab/stats

# delete
curl -X DELETE http://127.0.0.1:8000/api/links/schwab
```

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/shorten` | Create link. Body: `url`, optional `alias` (4–32 chars), optional `ttl_days` (1–365) |
| GET | `/{code}` | 307 redirect; records click. 404 if unknown/expired |
| GET | `/api/links/{code}/stats` | Total clicks, 7-day daily series, top referrers |
| DELETE | `/api/links/{code}` | Remove link (clicks cascade) |
| GET | `/health` | Liveness + DB check |

Errors: `422` invalid URL/alias, `409` alias taken, `429` rate limited
(10 creates/min/IP), `404` unknown or expired.

## Tests

```bash
python -m pytest tests/ -q
```

14 tests: happy paths, alias collisions, invalid inputs, expiry, delete cascade,
rate-limit window behavior, private-IP rejection. Each test runs against a fresh
temp database.

Lint gate: `python -m ruff check app tests` — clean at HEAD.

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
- **No pagination on stats** — referrer list capped at 10 instead.
