"""Per-IP sliding-window rate limiter."""
import math
import os
import time
from collections import defaultdict, deque

# ponytail: in-memory per-process; move to Redis when running >1 instance
_windows: dict[str, deque] = defaultdict(deque)

# A rate limit is genuinely environment-specific: a demo wants headroom, a
# public deployment wants it tight. Env var, so neither needs a code change.
LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", "10"))
WINDOW = 60.0    # seconds


def allow(ip: str, now: float | None = None) -> bool:
    now = now if now is not None else time.monotonic()
    q = _windows[ip]
    while q and now - q[0] > WINDOW:
        q.popleft()
    if len(q) >= LIMIT:
        return False
    q.append(now)
    return True


def retry_after(ip: str, now: float | None = None) -> int:
    """Seconds until the next request would be allowed. 0 if allowed now.

    The oldest request in the window is the one whose expiry frees a slot.
    """
    now = now if now is not None else time.monotonic()
    q = _windows[ip]
    if len(q) < LIMIT:
        return 0
    return max(1, math.ceil(q[0] + WINDOW - now))


def reset() -> None:
    _windows.clear()
