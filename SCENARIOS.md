# Scenarios

The three scenarios the brief asks for are scenarios 1–3. Scenario 4 is a second
brownfield increment added afterwards. Each maps to one git commit, so the diffs
are inspectable:

```
3bb57a1  Greenfield: core URL shortener
5cbadeb  Brownfield: click analytics
a3180d3  Ambiguous: "handle abuse" → rate limiting + internal-target guard
e85077e  Brownfield 2: demo console, QR, structured logging, CI
```

---

## Scenario 1 — Greenfield: core shortener

**Requirement:** "Build a URL shortener service with core APIs."

**Normalization.** "Core APIs" is underspecified. Normalized to: create
(with optional custom alias and TTL), redirect, delete, health. Explicitly
deferred: auth, bulk operations, QR codes — none implied by "core."

**Decomposition** (dependency order):

1. Persistence layer + schema (`db.py`) — everything depends on it
2. Code generation + input validation (`shortener.py`) — pure functions, no deps
3. HTTP layer wiring 1+2 (`main.py`)
4. API tests — written against the HTTP contract, not internals

**Execution highlights.**
- Collision strategy decided *before* generating code: insert-and-catch on the
  PK rather than check-then-insert, because the latter races under concurrency.
- 307 over 301: browsers cache 301 forever, which breaks expiry and delete.
- Random codes over sequential: sequential codes are enumerable — a stranger
  can walk every link in the system.

**Validation.** 8 tests: happy path, duplicate alias → 409, malformed
aliases/URLs → 422, unknown code → 404, delete lifecycle, forced expiry → 404,
health. All green before commit.

---

## Scenario 2 — Brownfield: add click analytics

**Requirement:** "Add analytics to the existing shortener."

**Codebase reasoning — impact analysis before edits:**

| Touched | Change | Risk |
|---|---|---|
| `db.py` schema | New `clicks` table + index | Additive; `CREATE IF NOT EXISTS` keeps existing DBs valid |
| Redirect path (`main.py`) | Record click before 307 | Adds write to hottest path — accepted at prototype scale, marked in code |
| Delete path | Clicks must not orphan | FK `ON DELETE CASCADE`; requires `PRAGMA foreign_keys=ON` (already set) |
| New endpoint | `GET /api/links/{code}/stats` | Read-only, low risk |

**Normalization.** "Analytics" scoped to: total clicks, 7-day daily series,
top-10 referrers. Rejected for scope: geo/device breakdown (needs a GeoIP
dependency), unique visitors (needs cookies/fingerprinting — privacy surface
not justified here).

**Validation.** 3 new tests: click counting with referrer attribution, stats
404, and — the regression that matters — delete cascades clicks. Prior 8 tests
untouched and green, demonstrating the change was additive.

---

## Scenario 3 — Ambiguous: "Make sure people can't abuse it"

**Requirement as given** — deliberately vague, as a stakeholder would say it.

**Ambiguity analysis.** "Abuse" could mean: (a) flooding the creation endpoint,
(b) using the shortener to mask links into internal infrastructure,
(c) malicious destination content (phishing/malware), (d) squatting on
meaningful aliases. Asked: which are exploitable *today* with only code?

**Normalization decision:**
- **(a) → build**: per-IP sliding-window rate limit, 10 creates/min. Sliding
  window over fixed window: fixed windows allow 2× burst at the boundary.
- **(b) → build**: reject destinations that are literal private/loopback/
  reserved IPs or `localhost`. Cheap, closes the obvious hole.
- **(c) → reject, documented**: real malware screening needs a threat-intel
  feed (e.g. Safe Browsing API) — an external dependency and API key, not a
  2-day-prototype item. Recorded as a limitation instead of faking it with a
  regex blocklist that would only provide false confidence.
- **(d) → already covered**: reserved-word guard from Scenario 1.

**Known residual gap, stated not hidden:** the IP guard doesn't resolve
domains, so `http://internal.corp` pointing at 10.x passes. Fixing this
properly (resolution at fetch time behind a proxy) is out of scope; resolving
at creation time is half a fix (DNS rebinding) and was rejected as false
safety.

**Validation.** 3 new tests: 11th request in a minute → 429; private targets →
422; window-slide + per-IP isolation via injected clock (no sleeps in the
suite). Full suite: 14 green.

---

## Scenario 4 — Brownfield, second increment: demo console + reliability

Added after the three required scenarios, on a real observation: the API was
correct but *unreviewable without curl*. A reviewer's first five minutes decide
whether the rest gets read, and `/docs` alone does not show that the security
guards work.

**Requirement, as I wrote it for myself:** "Make the system verifiable by
someone who has not read the code, in under two minutes, without a terminal."

**Decomposition:**

1. `GET /api/links` — the console needs a list endpoint; the API had none
2. `GET /api/links/{code}/qr` — QR as SVG via `segno`
3. `GET /` — static console page
4. Guided checks — each probe declares its expected status code before running
5. `RequestLogMiddleware` — correlation IDs and JSON access logs
6. GitHub Actions — run pytest and ruff on every push

**The design constraint that mattered.** The console calls only public API
endpoints — no privileged route, no server-rendered state. That keeps the API
as the single contract, so the demo cannot show something the API doesn't
actually do. It also means the page is a static file: no build step, no
framework, nothing for a reviewer to install.

**Why the guided checks name their expected status first.** A demo that just
shows green ticks proves nothing — the reader has to trust it. Declaring
"expect 422" *before* running, then showing the received status and the raw
response body, makes the assertion falsifiable on screen. These mirror the
pytest assertions, so the two agree by construction.

**A real bug this stage caught.** Wiring the QR route in, an edit landed on top
of the `/health` handler: its decorator was replaced and its body left as
unreachable code after the `return` in `qr()`. Tests still passed — nothing
covered `/health`'s absence at that moment, and the dead lines were valid
Python. Reading the full file rather than trusting the diff is what surfaced it.
The lesson is recorded here rather than quietly fixed: **AI-generated edits fail
in ways that stay syntactically valid, so a green suite is a floor, not a
ceiling.** `test_health` now covers it.

**Validation.** 6 new tests (console served, list with click counts, QR SVG, QR
404, request-ID generated, request-ID echoed). Full suite: 20 green, ruff clean.
Structured logging verified against a live server — a supplied
`X-Request-ID: demo-trace-1` appears in the emitted log line, and an unsupplied
one is generated. Console verified in a real browser at desktop and mobile
widths; a mobile layout overflow (grid children default to `min-width:auto` and
refuse to shrink) was found and fixed during that pass.
