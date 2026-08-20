"""URL shortener API."""
import io
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import segno
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from app import db, ratelimit, shortener
from app.logging_mw import RequestLogMiddleware

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="URL Shortener", version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestLogMiddleware)


class ShortenRequest(BaseModel):
    url: str = Field(..., examples=["https://example.com/some/long/path"])
    alias: str | None = Field(None, description="Optional custom code, 4-32 chars [A-Za-z0-9_-]")
    ttl_days: int | None = Field(None, ge=1, le=365, description="Days until expiry; omit for permanent")


class ShortenResponse(BaseModel):
    code: str
    short_url: str
    url: str
    expires_at: str | None


def _expired(row) -> bool:
    if row["expires_at"] is None:
        return False
    return datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc).replace(tzinfo=None)


@app.get("/", include_in_schema=False)
def console():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/links")
def list_links():
    return {"links": db.list_links()}


@app.get("/api/links/{code}/qr")
def qr(code: str, request: Request):
    if db.get_link(code) is None:
        raise HTTPException(404, "Unknown link")
    buf = io.BytesIO()
    segno.make(str(request.base_url) + code, error="m").save(buf, kind="svg", scale=4, dark="#001F3E")
    return Response(buf.getvalue(), media_type="image/svg+xml")


@app.get("/health")
def health():
    db.get_conn().execute("SELECT 1")
    return {"status": "ok"}


@app.post("/api/shorten", response_model=ShortenResponse, status_code=201)
def shorten(body: ShortenRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    if not ratelimit.allow(ip):
        wait = ratelimit.retry_after(ip)
        # RFC 6585: a 429 SHOULD tell the client when to come back.
        raise HTTPException(
            429,
            f"Rate limit exceeded: {ratelimit.LIMIT} links per minute. Try again in {wait}s.",
            headers={"Retry-After": str(wait)},
        )
    err = shortener.validate_url(body.url)
    if err:
        raise HTTPException(422, err)

    expires_at = None
    if body.ttl_days:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=body.ttl_days)).replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")

    if body.alias:
        if not shortener.valid_alias(body.alias):
            raise HTTPException(422, "Alias must be 4-32 chars [A-Za-z0-9_-] and not reserved")
        if not db.insert_link(body.alias, body.url, expires_at):
            raise HTTPException(409, "Alias already in use")
        code = body.alias
    else:
        for _ in range(5):  # collision retry; p(5 misses) is negligible
            code = shortener.generate_code()
            if db.insert_link(code, body.url, expires_at):
                break
        else:
            raise HTTPException(500, "Could not allocate a code")

    return ShortenResponse(
        code=code,
        short_url=str(request.base_url) + code,
        url=body.url,
        expires_at=expires_at,
    )


@app.get("/{code}")
def redirect(code: str, request: Request):
    row = db.get_link(code)
    if row is None or _expired(row):
        raise HTTPException(404, "Unknown or expired link")
    db.record_click(code, request.headers.get("referer"))
    # 307 keeps method + avoids permanent browser caching (lets us expire/delete later)
    return RedirectResponse(row["url"], status_code=307)


@app.get("/api/links/{code}/stats")
def stats(code: str):
    if db.get_link(code) is None:
        raise HTTPException(404, "Unknown link")
    return db.link_stats(code)


@app.delete("/api/links/{code}", status_code=204)
def delete(code: str):
    if not db.delete_link(code):
        raise HTTPException(404, "Unknown link")
