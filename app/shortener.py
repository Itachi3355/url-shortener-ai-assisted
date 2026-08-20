"""Code generation and URL validation."""
import ipaddress
import re
import secrets
import string
from urllib.parse import urlparse

ALPHABET = string.ascii_letters + string.digits  # base62
CODE_LEN = 7  # 62^7 ≈ 3.5e12 — collision-safe for prototype scale
ALIAS_RE = re.compile(r"^[A-Za-z0-9_-]{4,32}$")
RESERVED = {"api", "health", "docs", "openapi.json", "redoc"}


def generate_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))


def valid_alias(alias: str) -> bool:
    return bool(ALIAS_RE.match(alias)) and alias.lower() not in RESERVED


def validate_url(url: str) -> str | None:
    """Returns error message, or None if acceptable."""
    if len(url) > 2048:
        return "URL exceeds 2048 characters"
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return "Only http/https URLs are allowed"
    host = parsed.hostname
    if not host:
        return "URL has no hostname"
    # Abuse guard: refuse links into private/loopback space (open-redirect into intranets)
    if host == "localhost":
        return "Internal hostnames are not allowed"
    try:
        if not ipaddress.ip_address(host).is_global:
            return "Private or reserved IP targets are not allowed"
    except ValueError:
        pass  # a normal domain name, fine
    return None
