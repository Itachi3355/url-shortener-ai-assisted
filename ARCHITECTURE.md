# Architecture

## Components

```
browser ──▶ app/static/index.html   LinkDesk console (no build step, no framework)
   │              calls the same public API a third-party client would
   ▼
client ──▶ RequestLogMiddleware      request ID, JSON access log, duration
              │
           FastAPI (app/main.py)
              │  routes, request/response models, HTTP semantics
              ├─ app/shortener.py    code generation, URL/alias validation
              ├─ app/ratelimit.py    per-IP sliding window (in-memory)
              ├─ app/logging_mw.py   correlation IDs + structured logging
              └─ app/db.py           SQLite persistence (stdlib sqlite3, WAL)
                     │
                 shortener.db
                   links(code PK, url, created_at, expires_at)
                   clicks(id, code FK→links ON DELETE CASCADE, ts, referrer)
```

The console is a *client*, not a layer: it holds no state and has no privileged
endpoint. Everything it does is a documented public API call, so the demo cannot
drift from what the API actually offers.

Control flow, create: `POST /api/shorten` → rate-limit check → URL validation →
alias validation or base62 generation → insert (PK collision = retry or 409) →
response with short URL.

Control flow, redirect: `GET /{code}` → lookup → expiry check → record click →
`307` to target.

## Key decisions

| Decision | Choice | Why | Rejected alternative |
|---|---|---|---|
| Framework | FastAPI | Typed request models give validation for free; OpenAPI docs at `/docs` are a built-in demo surface | Flask (manual validation), Django (too heavy for 4 endpoints) |
| Storage | SQLite via stdlib | Zero setup for a runnable prototype; WAL mode handles concurrent readers; schema is 2 tables | SQLAlchemy + Postgres — an ORM over 6 queries is ceremony, and Postgres breaks "clone and run" |
| Code generation | Random base62, length 7, `secrets` | 62⁷ ≈ 3.5×10¹² keyspace; random codes aren't enumerable (sequential codes let strangers walk your links) | Sequential + base62 encode (enumerable), hash of URL (dedup coupling, truncation collisions) |
| Redirect status | 307 | Browsers cache 301 permanently — an expired or deleted link would keep redirecting from cache | 301 (better for SEO, wrong for mutable links) |
| Collision handling | Insert-and-catch `IntegrityError`, retry ×5 | Check-then-insert races; DB PK is the only honest uniqueness authority | SELECT-then-INSERT (TOCTOU race) |
| Analytics write | Sync insert on redirect | ~1ms on SQLite; correctness first, marked with upgrade path | Background queue — premature at prototype scale |
| Rate limiter | In-memory sliding window deque | Correct within one process, testable with injected clock; honest `ponytail:` marker points to Redis | Redis (new infra dependency for a prototype), fixed window (burst-at-boundary artifact) |
| Expiry | Lazy check on read | No background job needed; expired rows are invisible immediately | Cron sweeper — adds a moving part; can be added later purely for storage hygiene |
| Console UI | One static HTML file, vanilla JS | Reviewer clones and opens a browser — no npm install, no build, nothing to go stale. Keeps the API as the only contract | React/Vite SPA — a build pipeline and 200MB of dependencies to demonstrate four endpoints |
| QR generation | `segno`, rendered as SVG on demand | Pure-Python, no system libraries (Pillow/libz would break "clone and run" on some machines); SVG scales and stays crisp | Pillow PNG (binary dependency), client-side JS library (another script to vendor) |
| Access logging | JSON lines to stdout, one per request | Aggregators index fields directly; stdout is the correct sink for a container | Formatted text logs (need regex parsing), log file on disk (rotation becomes my problem) |
| Correlation ID | Honor inbound `X-Request-ID`, else generate | A trace ID from an upstream gateway survives into these logs instead of restarting at the edge | Always generate — silently breaks distributed tracing |

## Scaling path (not built, by design)

1. Postgres for links/clicks; connection pool.
2. Redis: rate-limit state + cache of hot code→URL mappings (redirects are
   read-heavy and immutable until deleted).
3. Click ingestion via queue; aggregate table for stats instead of COUNT scans.
4. API-key auth on management endpoints.

## Security posture

- `secrets` for code generation (not `random`).
- Parameterized SQL throughout; no string-built queries.
- Scheme allowlist (`http`/`https`) blocks `javascript:`/`data:` payloads.
- Private/loopback/reserved IP destinations rejected (see README for the
  DNS-resolution gap that remains).
- Reserved-word alias guard prevents shadowing `/api`, `/docs`, `/health`.
