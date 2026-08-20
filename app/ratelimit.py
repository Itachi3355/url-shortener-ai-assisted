"""Per-IP sliding-window rate limiter."""
import time
from collections import defaultdict, deque

# ponytail: in-memory per-process; move to Redis when running >1 instance
_windows: dict[str, deque] = defaultdict(deque)

LIMIT = 10       # requests
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


def reset() -> None:
    _windows.clear()
