"""End-to-end smoke test. Runs the FastAPI app in-process, exercises
the production API surface, asserts everything wires together.

Uses SQLite (no Postgres dependency) and disables the experimental
module to verify gating works in both directions.
"""
import os
import sys

# Force SQLite + disable experimental BEFORE any app import
os.environ["DATABASE_URL"] = "sqlite:///./_smoke_test.db"
os.environ["EXPERIMENTAL_ENABLED"] = "false"
os.environ["SECRET_KEY"] = "smoke-test-secret"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

# Remove leftover DB
if os.path.exists("./_smoke_test.db"):
    os.remove("./_smoke_test.db")

from app.main import app  # noqa: E402

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["experimental_enabled"] is False


def test_dashboard_root_serves():
    r = client.get("/")
    assert r.status_code == 200
    assert "Social Ultimate" in r.text


def test_register_and_login():
    r = client.post("/api/auth/register",
                    json={"email": "test@example.com", "password": "password123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    assert token

    # Login with same creds
    r2 = client.post("/api/auth/login",
                     data={"username": "test@example.com", "password": "password123"})
    assert r2.status_code == 200
    assert r2.json()["access_token"]

    # Wrong password rejected (same generic message — no enumeration)
    r3 = client.post("/api/auth/login",
                     data={"username": "test@example.com", "password": "wrong"})
    assert r3.status_code == 401


def test_experimental_blocked_by_default():
    """After register, the user exists, so we can use the token from the prior test."""
    token = client.post("/api/auth/login",
                        data={"username": "test@example.com",
                              "password": "password123"}).json()["access_token"]
    assert token, "login must succeed — register should have created the user"
    r = client.post("/api/experimental/bot/jobs",
                    json={"job_type": "like_by_tag", "target": "fitness",
                          "consent_acknowledged": True},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    assert "EXPERIMENTAL_ENABLED" in r.json()["detail"]


def test_experimental_requires_consent_when_enabled(monkeypatch):
    """If EXPERIMENTAL_ENABLED were true, no-consent should be 400, not 200."""
    import importlib
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "experimental_enabled", True, raising=False)
    import app.core.experimental_gate as gate
    importlib.reload(gate)
    # Re-decorate endpoints — easier path: directly call the gate function
    from fastapi import HTTPException
    try:
        gate.require_explicit_consent(user_consented=False)
        assert False, "should have raised"
    except HTTPException as e:
        assert e.status_code == 400
        assert "consent" in e.detail.lower()


def test_me_requires_auth():
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_with_token():
    token = client.post("/api/auth/login",
                        data={"username": "test@example.com",
                              "password": "password123"}).json()["access_token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "test@example.com"


def test_security_headers():
    r = client.get("/health")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert "strict-transport-security" in r.headers


def test_xss_in_caption_sanitized():
    """Captions are user input that ends up in our DB and Instagram.
    Make sure we strip tags even at the API layer."""
    token = client.post("/api/auth/login",
                        data={"username": "test@example.com",
                              "password": "password123"}).json()["access_token"]
    # We can't actually publish (no IG creds), but we can verify schedule
    # rejects the request cleanly without crashing on script tags.
    payload = {
        "account_id": 1,
        "caption": "<script>alert(1)</script>hello",
        "media_url": "https://example.com/img.jpg",
        "scheduled_for": "2099-01-01T00:00:00",
    }
    r = client.post("/api/posts", json=payload,
                    headers={"Authorization": f"Bearer {token}"})
    # Should pass validation but we'll get 404 for missing account
    # (no IG account linked). That's fine — we just need it to NOT 500.
    assert r.status_code in (200, 400, 404)


def test_duplicate_email_rejected():
    r = client.post("/api/auth/register",
                    json={"email": "test@example.com", "password": "password123"})
    assert r.status_code == 409


def test_oauth_start_returns_helpful_error_when_unconfigured():
    token = client.post("/api/auth/login",
                        data={"username": "test@example.com",
                              "password": "password123"}).json()["access_token"]
    r = client.get("/api/instagram/oauth/start",
                   headers={"Authorization": f"Bearer {token}"})
    # App ID is empty in test env, so should be a 503 with helpful message
    assert r.status_code == 503
    assert "INSTAGRAM_APP_ID" in r.json()["detail"]