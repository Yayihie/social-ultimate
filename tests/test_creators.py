"""Tests for the real account creators — driver-injected so no browser needed.

Verifies:
- driver_utils: identity generators + make_driver raises helpful error
  when selenium isn't installed (we test the error path since we can't
  easily run a real browser in CI)
- instagram_creator: returns a structured failure when fake-email service
  is unreachable, instead of crashing
- facebook_creator: same
- API: gating works for both platforms
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_creators.db")
os.environ.setdefault("SECRET_KEY", "test")


@pytest.fixture(autouse=True)
def enable_experimental_for_creators_tests():
    """Force EXPERIMENTAL_ENABLED=true for these tests, restore after."""
    import app.core.config as _cfg
    original = _cfg.settings.experimental_enabled
    _cfg.settings.experimental_enabled = True
    yield
    _cfg.settings.experimental_enabled = original


def test_driver_utils_identity_generators():
    from app.experimental.driver_utils import (
        random_first_name, random_last_name, random_full_name,
        random_username, random_password, random_birthday,
    )
    assert isinstance(random_first_name(), str) and len(random_first_name()) > 1
    assert isinstance(random_last_name(), str)
    fn, ln = random_full_name().split()
    assert isinstance(fn, str) and isinstance(ln, str)
    u = random_username()
    assert "_" in u
    p = random_password()
    assert len(p) >= 10
    y, m, d = random_birthday()
    assert 1980 < y < 2005
    assert 1 <= m <= 12
    assert 1 <= d <= 31


def test_make_driver_missing_selenium():
    """When selenium isn't importable, raises a helpful RuntimeError."""
    from app.experimental.driver_utils import make_driver, DriverOptions
    with patch.dict(sys.modules, {"selenium": None, "selenium.webdriver": None,
                                  "selenium.webdriver.chrome": None,
                                  "selenium.webdriver.chrome.options": None,
                                  "selenium.webdriver.chrome.service": None}):
        with pytest.raises(RuntimeError, match="Selenium is not installed"):
            make_driver(DriverOptions(headless=True))


def test_instagram_creator_email_fetch_failure():
    """If mailbox backend is down, we get a structured failure, not a crash."""
    from app.experimental.instagram_creator import create_instagram_account
    # ConsoleBackend never fails — we need to test the failure path differently.
    # Patch make_mailbox to return a broken mailbox.
    class BrokenMailbox:
        def get_address(self):
            raise RuntimeError("network down")
        def backend_name(self):
            return "broken"
        def fetch_messages(self, since_id=None):
            raise RuntimeError("network down")
    with patch("app.experimental.instagram_creator.make_mailbox", return_value=BrokenMailbox()):
        result = create_instagram_account(user_id=999, db_url="sqlite:///./_x.db")
        assert result.account.success is False
        assert "network down" in result.account.error
        # identity was still generated
        assert result.account.username
        assert result.account.full_name


def test_facebook_creator_email_fetch_failure():
    from app.experimental.facebook_creator import create_facebook_account
    class BrokenMailbox:
        def get_address(self):
            raise RuntimeError("network down")
        def backend_name(self):
            return "broken"
        def fetch_messages(self, since_id=None):
            raise RuntimeError("network down")
    with patch("app.experimental.facebook_creator.make_mailbox", return_value=BrokenMailbox()):
        result = create_facebook_account(user_id=999, db_url="sqlite:///./_x.db")
        assert result.account.success is False
        assert "network down" in result.account.error
        assert result.account.first_name  # identity was generated before email fetch failed


def test_facebook_creator_invalid_platform_via_api():
    """API rejects bad platform values."""
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    c.post("/api/auth/register", json={"email": "fb@test.com", "password": "password123"})
    token = c.post("/api/auth/login",
                   data={"username": "fb@test.com", "password": "password123"}).json()["access_token"]
    r = c.post("/api/experimental/accounts/create",
               json={"platform": "tiktok", "count": 1, "consent_acknowledged": True},
               headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400
    assert "platform" in r.json()["detail"]


def test_facebook_creator_rejects_count_over_10():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    c.post("/api/auth/register", json={"email": "cnt@test.com", "password": "password123"})
    token = c.post("/api/auth/login",
                   data={"username": "cnt@test.com", "password": "password123"}).json()["access_token"]
    r = c.post("/api/experimental/accounts/create",
               json={"platform": "facebook", "count": 100, "consent_acknowledged": True},
               headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400
    assert "count" in r.json()["detail"]


def test_facebook_creator_requires_consent():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    c.post("/api/auth/register", json={"email": "c2@test.com", "password": "password123"})
    token = c.post("/api/auth/login",
                   data={"username": "c2@test.com", "password": "password123"}).json()["access_token"]
    r = c.post("/api/experimental/accounts/create",
               json={"platform": "facebook", "count": 1, "consent_acknowledged": False},
               headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400
    assert "consent" in r.json()["detail"].lower()


def test_backward_compat_account_creator_stub():
    """The deprecated AccountCreator wrapper still works for old imports."""
    from app.experimental.account_creator import (
        AccountCreator, generate_username, generate_password, generate_user_info,
    )
    creator = AccountCreator(driver=None)
    info = generate_user_info()
    assert "username" in info and "password" in info
    result = creator.create_one(info)
    assert result.success is False
    assert "deprecated" in result.error.lower() or "directly" in result.error.lower()