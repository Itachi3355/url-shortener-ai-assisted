"""Per-IP sliding-window rate limiter."""
import math
import os
import time
from collections import defaultdict, deque

# ponytail: in-memory per-process; move to Redis when running >1 instance
_windows: dict[str, deque] = defaultdict(deque)

WINDOW = 60.0    # seconds
DEFAULT_LIMIT = 10


def _parse_limit() -> int:
    """A rate limit is genuinely environment-specific: a demo wants headroom, a
    public deployment wants it tight. Env var, so neither needs a code change.

    Misconfiguration fails at import with a message naming the variable, rather
    than a bare int() traceback. A non-positive limit is floored to 1: it would
    otherwise block every request, which is never what an operator meant.
    """
    raw = os.getenv("RATE_LIMIT_PER_MIN")
    if raw is None or not raw.strip():
        return DEFAULT_LIMIT
    try:
        value = int(raw.strip())
    except ValueError:
        raise ValueError(
            f"RATE_LIMIT_PER_MIN must be a whole number of requests, got {raw!r}"
        ) from None
    return max(1, value)


LIMIT = _parse_limit()


def _prune(q: deque, now: float) -> deque:
    """Drop timestamps that have aged out of the window."""
    while q and now - q[0] > WINDOW:
        q.popleft()
    return q


def allow(ip: str, now: float | None = None) -> bool:
    now = now if now is not None else time.monotonic()
    q = _prune(_windows[ip], now)
    if len(q) >= LIMIT:
        return False
    q.append(now)
    return True


def retry_after(ip: str, now: float | None = None) -> int:
    """Seconds until the next request would be allowed. 0 if allowed now.

    The oldest request in the window is the one whose expiry frees a slot.
    Prunes first, so the answer agrees with allow() even when this is called
    standalone after a full window has elapsed.
    """
    now = now if now is not None else time.monotonic()
    q = _prune(_windows[ip], now)
    if not q or len(q) < LIMIT:
        return 0
    return max(1, math.ceil(q[0] + WINDOW - now))


def reset() -> None:
    _windows.clear()
