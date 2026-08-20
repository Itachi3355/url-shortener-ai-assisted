# Three Scenarios

Each scenario maps to one git commit, so the diffs are inspectable:

```
3bb57a1  Greenfield: core URL shortener
5cbadeb  Brownfield: click analytics
a3180d3  Ambiguous: "handle abuse" → rate limiting + internal-target guard
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
