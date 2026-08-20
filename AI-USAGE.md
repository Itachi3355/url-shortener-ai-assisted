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
| Test suite (14 tests) | AI generated from acceptance criteria per stage | **Reviewed each assertion** — notably verified `test_delete_cascades_clicks` queries the DB directly rather than trusting the API's 204 |
| Docs (README/ARCHITECTURE/SCENARIOS) | AI drafted | **Reviewed for honesty** — limitations section states real gaps (DNS-rebinding SSRF, single-process limiter) rather than marketing the prototype |

## Quality gates applied

- **Tests:** full suite after every stage; nothing committed red. 14/14 green at HEAD.
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
