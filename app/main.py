"""URL shortener API."""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app import db, shortener


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="URL Shortener", version="0.1.0", lifespan=lifespan)


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


@app.get("/health")
def health():
    db.get_conn().execute("SELECT 1")
    return {"status": "ok"}


@app.post("/api/shorten", response_model=ShortenResponse, status_code=201)
def shorten(body: ShortenRequest, request: Request):
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
def redirect(code: str):
    row = db.get_link(code)
    if row is None or _expired(row):
        raise HTTPException(404, "Unknown or expired link")
    # 307 keeps method + avoids permanent browser caching (lets us expire/delete later)
    return RedirectResponse(row["url"], status_code=307)


@app.delete("/api/links/{code}", status_code=204)
def delete(code: str):
    if not db.delete_link(code):
        raise HTTPException(404, "Unknown link")
