import pytest
from fastapi.testclient import TestClient

from app import db, ratelimit


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db, "_local", type(db._local)())  # fresh thread-local per test
    ratelimit.reset()
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_shorten_and_redirect(client):
    r = client.post("/api/shorten", json={"url": "https://example.com/x"})
    assert r.status_code == 201
    code = r.json()["code"]
    assert len(code) == 7

    r = client.get(f"/{code}", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "https://example.com/x"


def test_custom_alias(client):
    r = client.post("/api/shorten", json={"url": "https://example.com", "alias": "my-link"})
    assert r.status_code == 201
    assert r.json()["code"] == "my-link"
    # duplicate alias rejected
    r = client.post("/api/shorten", json={"url": "https://example.com", "alias": "my-link"})
    assert r.status_code == 409


def test_bad_alias_rejected(client):
    for alias in ["ab", "has space", "api", "x" * 33]:
        r = client.post("/api/shorten", json={"url": "https://example.com", "alias": alias})
        assert r.status_code == 422, alias


def test_invalid_url_rejected(client):
    for url in ["ftp://example.com", "javascript:alert(1)", "notaurl", "https://" ]:
        r = client.post("/api/shorten", json={"url": url})
        assert r.status_code == 422, url


def test_unknown_code_404(client):
    assert client.get("/nope123", follow_redirects=False).status_code == 404


def test_delete(client):
    code = client.post("/api/shorten", json={"url": "https://example.com"}).json()["code"]
    assert client.delete(f"/api/links/{code}").status_code == 204
    assert client.get(f"/{code}", follow_redirects=False).status_code == 404
    assert client.delete(f"/api/links/{code}").status_code == 404


def test_expired_link_404(client):
    code = client.post("/api/shorten", json={"url": "https://example.com", "ttl_days": 1}).json()["code"]
    # force-expire in DB
    with db.get_conn() as conn:
        conn.execute("UPDATE links SET expires_at = '2000-01-01 00:00:00' WHERE code = ?", (code,))
    assert client.get(f"/{code}", follow_redirects=False).status_code == 404


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_stats_counts_clicks_and_referrers(client):
    code = client.post("/api/shorten", json={"url": "https://example.com"}).json()["code"]
    client.get(f"/{code}", follow_redirects=False)
    client.get(f"/{code}", follow_redirects=False, headers={"referer": "https://news.site"})
    s = client.get(f"/api/links/{code}/stats").json()
    assert s["total_clicks"] == 2
    assert sum(d["clicks"] for d in s["last_7_days"]) == 2
    refs = {r["referrer"]: r["clicks"] for r in s["top_referrers"]}
    assert refs == {"(direct)": 1, "https://news.site": 1}


def test_stats_unknown_code_404(client):
    assert client.get("/api/links/nope123/stats").status_code == 404


def test_delete_cascades_clicks(client):
    code = client.post("/api/shorten", json={"url": "https://example.com"}).json()["code"]
    client.get(f"/{code}", follow_redirects=False)
    client.delete(f"/api/links/{code}")
    n = db.get_conn().execute("SELECT COUNT(*) FROM clicks WHERE code = ?", (code,)).fetchone()[0]
    assert n == 0


def test_rate_limit_429(client):
    for i in range(ratelimit.LIMIT):
        assert client.post("/api/shorten", json={"url": "https://example.com"}).status_code == 201
    assert client.post("/api/shorten", json={"url": "https://example.com"}).status_code == 429


def test_private_targets_rejected(client):
    ratelimit.reset()
    for url in ["http://localhost/admin", "http://127.0.0.1:8080/", "http://10.0.0.5/", "http://192.168.1.1/"]:
        r = client.post("/api/shorten", json={"url": url})
        assert r.status_code == 422, url


def test_rate_limit_window_slides():
    ratelimit.reset()
    for _ in range(ratelimit.LIMIT):
        assert ratelimit.allow("1.2.3.4", now=100.0)
    assert not ratelimit.allow("1.2.3.4", now=100.0)
    assert ratelimit.allow("1.2.3.4", now=100.0 + ratelimit.WINDOW + 1)
    assert ratelimit.allow("5.6.7.8", now=100.0)  # per-IP isolation
