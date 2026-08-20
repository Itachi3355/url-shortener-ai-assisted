# AI Usage Log

How AI (Claude, via Claude Code) was used, with traceability per the
generated / edited / rejected discipline. Principle applied throughout: **AI
drafts within a task I define; I own correctness and sign off before each
commit.**

## Working method

Every task given to the AI carried four parts:

1. **Intent** — what the change accomplishes ("record clicks so stats can be served")
2. **Constraints** — stack, style, what *not* to do ("stdlib sqlite3, no ORM; no new dependencies")
3. **Acceptance criteria** — observable outcomes ("11th request in 60s returns 429; suite stays green")
4. **Technical context** — the files in play and current schema

Each stage ended with a quality gate before commit:
run full test suite → review the diff line-by-line → check security posture
(injection, randomness source, input validation) → commit with a message
recording scope and rationale.

## Traceability table

| Artifact | Origin | Engineer action + rationale |
|---|---|---|
| `db.py` insert-and-catch collision handling | AI generated after I specified the approach | **Accepted.** I chose insert-and-catch over check-then-insert before generation — check-then-insert has a TOCTOU race |
| `shortener.py` code generation | AI generated | **Edited direction:** required `secrets` over `random` in the constraints — predictable codes are enumerable |
| Redirect status code | AI initially proposed 301 (conventional for shorteners) | **Rejected → 307.** 301 is permanently cached by browsers; breaks expiry/delete. Comment in code records this |
| Pydantic request models | AI generated | **Accepted** after verifying bounds (`ttl_days` 1–365, alias regex anchored both ends) |
| ORM / SQLAlchemy layer | AI offered as option | **Rejected.** Six queries don't justify an ORM; stdlib keeps setup at `pip install` + run |
| `clicks` schema + stats queries | AI generated from my column spec | **Edited:** added `idx_clicks_code_ts` — stats queries filter on `(code, ts)`, unindexed would table-scan |
| Delete/clicks orphan handling | I identified the gap during impact analysis | AI implemented FK CASCADE; I verified `PRAGMA foreign_keys=ON` was actually set (SQLite defaults it OFF — classic silent failure) |
| Rate limiter | AI generated to my spec (sliding window, injectable clock) | **Accepted.** Injectable `now` was in the acceptance criteria so tests need no sleeps |
| Regex-blocklist "malware filter" | Considered for the abuse scenario | **Rejected as false safety.** A keyword blocklist looks like security and isn't; recorded the real solution (threat-intel API) as a limitation instead |
| Test suite (20 tests) | AI generated from acceptance criteria per stage | **Reviewed each assertion** — notably verified `test_delete_cascades_clicks` queries the DB directly rather than trusting the API's 204 |
| Console UI (`static/index.html`) | AI generated to my spec: one static file, no framework, public endpoints only | **Accepted after constraining it.** The "no build step" rule was mine — a React SPA would make the reviewer run npm before seeing anything |
| Guided checks design | AI proposed buttons that showed a green tick on success | **Rejected → redesigned.** A tick the reader must trust proves nothing; each check now declares its expected status code before running and prints the raw response |
| `/health` clobbered by a QR-route edit | AI edit replaced the handler; its body survived as unreachable code | **Caught in review, not by tests.** Found by reading the whole file; the suite was green because nothing asserted `/health` existed. Documented in SCENARIOS.md rather than quietly fixed |
| Mobile layout overflow | Found by me during live browser verification | AI applied the fix (`min-width:0` on grid children); I verified `scrollWidth == clientWidth` at 375px afterwards rather than trusting the change |
| QR library choice | AI suggested Pillow-based generation | **Rejected → `segno`.** Pillow pulls binary dependencies that break "clone and run"; segno is pure Python and emits SVG |
| Structured logging middleware | AI generated to my spec | **Edited:** the draft always generated a request ID. Changed to honor an inbound `X-Request-ID` first — always generating silently breaks upstream tracing |
| CI workflow | AI generated | **Accepted.** Added specifically so the "quality gates" claim in this document is enforced by CI rather than asserted in prose |
| `Retry-After` on 429 | Gap found by me while demoing, not by tests | The suite asserted the 429 status and stopped there. Using the product showed the response was unusable to a client — RFC 6585 says a 429 SHOULD say when to retry. AI implemented `retry_after()`; I specified computing it from the oldest request in the sliding window rather than returning a flat 60 |
| Rate limit as env var | Mine | A hardcoded limit forces a code change to run a demo. `RATE_LIMIT_PER_MIN` is the one value here that genuinely differs per environment, so it is the one value that became config |
| Console fetch error handling | AI-generated console code read response fields without checking status | **Rejected the original.** A user hit `TypeError: Cannot read properties of undefined`. Root cause: three call sites each assumed the success shape, and an error body is `{"detail": …}`. Fixed once in a shared `getJSON()` that throws on non-2xx, rather than guarding the one function that reported the crash |
| Stale-row bug behind it | Found by tracing the report, not from the stack trace | `loadLinks()` early-returned when the list was empty, leaving deleted rows on screen to be clicked. The visible crash was the second bug; this was the first |
| Stats placement | AI put stats in a fixed panel above the table; a user pointed out it reads as disconnected from the row clicked | **Redesigned.** Stats now expand as a detail row directly beneath their own link, with a 7-day bar chart and referrer breakdown, and the button toggles to *Hide*. Attribution should not be something the reader has to reconstruct |
| CSS class collision | Caught by a `TypeError` in my own verification script, not by looking at the page | The new chart bars used `.bar`, which the page header already used for its layout row — so chart styles were silently restyling the header. Renamed to `.cbar*`; verified the header is back to its 64px height. Generated CSS lands in a global namespace and will collide with what is already there |
| Output escaping in the console | Neither AI nor the report raised it — found while reading the surrounding code | Destinations are attacker-controlled text interpolated into `innerHTML`. The scheme allowlist stops `javascript:` URLs but not quotes or angle brackets in a path, so a shortened link could inject markup into the console. Added `esc()`; verified a probe payload renders as text with zero injected elements |
| Docs (README/ARCHITECTURE/SCENARIOS) | AI drafted | **Reviewed for honesty** — limitations section states real gaps (DNS-rebinding SSRF, single-process limiter) rather than marketing the prototype |

## Quality gates applied

- **Tests:** full suite after every stage; nothing committed red. 20/20 green at HEAD.
- **CI:** pytest and ruff run on every push (`.github/workflows/ci.yml`), so
  these gates are enforced rather than self-reported.
- **Live verification:** the console was driven in a real browser — create flow,
  all seven checks, QR rendering, and responsive behavior at 375px and 1280px —
  not just asserted through `TestClient`.
- **Review:** every AI diff read before commit; deliberate shortcuts marked
  in-code with `ponytail:` comments naming the ceiling and upgrade path.
- **Security:** parameterized SQL only; `secrets` RNG; scheme allowlist;
  private-IP guard; reserved aliases. Residual risks documented, not hidden.
- **Sign-off:** three commits, one per scenario, each a reviewed unit.

## Secure AI usage

- No credentials, internal hostnames, or proprietary data in prompts.
- AI output treated as untrusted until reviewed — same bar as a PR from an
  unfamiliar contributor.
- High-impact choices (status-code semantics, security guards, schema) decided
  or explicitly ratified by the engineer, never auto-accepted.

## Where AI helped most / least

**Most:** test generation from acceptance criteria (fast, thorough on edge
cases I'd have skipped under time pressure); boilerplate-free FastAPI wiring;
documentation drafting.

**Least:** scoping decisions. "What does 'abuse' mean here" and "what is
honest to leave out" were engineering-judgment calls AI could enumerate
options for but not own.

**Most instructive:** the clobbered `/health` handler. AI edits fail in ways
that stay syntactically valid and keep the test suite green — the failure mode
is silent, not loud. That is the concrete argument for engineer review of every
diff, and the reason the review step is a gate here rather than a formality.
