"""Tests for mailbox abstraction + inbox persistence + code visibility."""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_mailbox.db")
os.environ.setdefault("SECRET_KEY", "test")


@pytest.fixture(autouse=True)
def enable_experimental_for_creators_tests():
    import app.core.config as _cfg
    original = _cfg.settings.experimental_enabled
    _cfg.settings.experimental_enabled = True
    yield
    _cfg.settings.experimental_enabled = original


def test_inbox_message_extracts_codes_from_ig_email():
    from app.experimental.mailbox import InboxMessage
    body = """
    Hi there,
    Your Instagram confirmation code is: 847291
    Or use this link: https://instagram.com/confirm/x
    """
    m = InboxMessage(
        sender="no-reply@mail.instagram.com",
        subject="Confirm your email",
        body=body,
        received_at=0.0,
        message_id="1",
    )
    codes = m.extract_codes()
    assert "847291" in codes


def test_inbox_message_extracts_alternative_format():
    from app.experimental.mailbox import InboxMessage
    body = "Welcome to Facebook! Your confirmation code is 451827."
    m = InboxMessage(sender="register@facebookmail.com", subject="Confirm",
                     body=body, received_at=0.0, message_id="1")
    assert "451827" in m.extract_codes()


def test_inbox_message_handles_empty_body():
    from app.experimental.mailbox import InboxMessage
    m = InboxMessage(sender="x", subject="y", body="", received_at=0.0, message_id="1")
    assert m.extract_codes() == []


def test_console_backend_injects_and_returns_messages():
    from app.experimental.mailbox import ConsoleBackend
    mb = ConsoleBackend(address="test@x.com")
    assert mb.get_address() == "test@x.com"
    assert mb.fetch_messages() == []
    mb.inject_message(sender="instagram", subject="Verify",
                      body="Your code is 123456")
    msgs = mb.fetch_messages()
    assert len(msgs) == 1
    assert "123456" in msgs[0].extract_codes()
    assert mb.backend_name() == "console"


def test_make_mailbox_dispatches_correctly():
    from app.experimental.mailbox import (
        make_mailbox, ConsoleBackend, GuerrillaMailBackend, EmailFakeBackend,
    )
    assert isinstance(make_mailbox("console"), ConsoleBackend)
    assert isinstance(make_mailbox("guerrillamail"), GuerrillaMailBackend)
    assert isinstance(make_mailbox("emailfake"), EmailFakeBackend)
    with pytest.raises(ValueError, match="Unknown backend"):
        make_mailbox("nonexistent")


def test_wait_for_code_returns_message_when_present():
    """wait_for_code polls mailbox and returns on match."""
    from app.experimental.mailbox import ConsoleBackend, wait_for_code
    mb = ConsoleBackend()
    events = []

    def cb(payload):
        events.append(payload)

    # Pre-inject so it's already there
    mb.inject_message(sender="no-reply@mail.instagram.com",
                      subject="Confirm", body="Your code is 555111")
    msg = wait_for_code(mb, sender_filter="instagram", timeout_seconds=5,
                        poll_interval=0.2, progress_callback=cb)
    assert msg is not None
    assert "555111" in msg.extract_codes()
    assert any(e.get("event") == "message_received" for e in events)


def test_wait_for_code_times_out_returns_none():
    from app.experimental.mailbox import ConsoleBackend, wait_for_code
    mb = ConsoleBackend()
    msg = wait_for_code(mb, sender_filter="instagram", timeout_seconds=1,
                        poll_interval=0.3)
    assert msg is None


def test_inbox_snapshots_api_endpoint():
    """Test the /api/experimental/inbox endpoint persists + returns snapshots."""
    from datetime import datetime
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)

    # Register & login
    c.post("/api/auth/register", json={"email": "inbox@test.com", "password": "password123"})
    token = c.post("/api/auth/login",
                   data={"username": "inbox@test.com", "password": "password123"}).json()["access_token"]

    # Directly insert via API internal session
    from app.db.session import SessionLocal
    from app.db.models import InboxSnapshot
    db = SessionLocal()
    try:
        from app.db.models import User
        user = db.query(User).filter(User.email == "inbox@test.com").first()
        snap = InboxSnapshot(
            user_id=user.id,
            backend="guerrillamail",
            email_address="abc@guerrillamailblock.com",
            sender="no-reply@mail.instagram.com",
            subject="Your Instagram code",
            body_excerpt="Your code is 847291",
            body_full="Your Instagram confirmation code is 847291",
            extracted_codes=["847291"],
            message_id="12345",
            event="message_received",
        )
        db.add(snap)
        db.commit()
    finally:
        db.close()

    # GET inbox
    r = c.get("/api/experimental/inbox", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1
    target = next((m for m in rows if m["message_id"] == "12345"), None)
    assert target is not None
    assert "847291" in target["extracted_codes"]

    # codes_only filter
    r2 = c.get("/api/experimental/inbox?codes_only=true",
               headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert any("847291" in m["extracted_codes"] for m in r2.json())

    # latest-codes shortcut
    r3 = c.get("/api/experimental/inbox/latest-codes",
               headers={"Authorization": f"Bearer {token}"})
    assert r3.status_code == 200
    codes_data = r3.json()
    assert any("847291" in entry["codes"] for entry in codes_data)


def test_account_creation_rejects_bad_mailbox_backend():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    c.post("/api/auth/register", json={"email": "mb@test.com", "password": "password123"})
    token = c.post("/api/auth/login",
                   data={"username": "mb@test.com", "password": "password123"}).json()["access_token"]
    r = c.post("/api/experimental/accounts/create",
               json={"platform": "instagram", "count": 1, "consent_acknowledged": True,
                     "mailbox_backend": "totally-fake-backend"},
               headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400
    assert "mailbox_backend" in r.json()["detail"]


def test_account_record_persists_mailbox_backend():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    c.post("/api/auth/register", json={"email": "rec@test.com", "password": "password123"})
    token = c.post("/api/auth/login",
                   data={"username": "rec@test.com", "password": "password123"}).json()["access_token"]

    # Queue a creation (BG task will fail because no selenium, but record is created)
    r = c.post("/api/experimental/accounts/create",
               json={"platform": "instagram", "count": 1, "consent_acknowledged": True,
                     "mailbox_backend": "console"},
               headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    # The placeholder record includes the mailbox backend
    body = r.json()
    assert body[0]["mailbox_backend"] == "console"