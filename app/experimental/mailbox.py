"""Mailbox abstraction for disposable email services.

Two backends supported, with a pluggable interface so you can add more:

1. **GuerrillaMailBackend** (default, recommended) — JSON API at
   api.guerrillamail.com. Reliable, used by many open-source tools.
   Inboxes auto-delete after 1 hour.

2. **EmailFakeBackend** (legacy) — what eaabak/instagram-auto-create-account
   used. Scrapes email-fake.com. Unreliable in 2026 — frequently returns
   Cloudflare challenges or empty responses. Kept for reference.

3. **ConsoleBackend** — returns a fixed address and never receives mail.
   Useful for testing the verification flow against a manual email
   you control, or for running the creator in 'observe only' mode.

The Mailbox base class always returns:
- An email address (str)
- A list of InboxMessage records with subject, body, sender, received_at
- The raw provider response for debugging (exposed via /api/experimental/inbox/<id>)
"""
from __future__ import annotations
import re
import time
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class InboxMessage:
    sender: str
    subject: str
    body: str
    received_at: float  # unix timestamp
    message_id: str  # provider-specific id, for retrieving this specific email later
    raw: dict = field(default_factory=dict)  # full provider response for debugging

    def extract_codes(self) -> list[str]:
        """Pull all plausible verification codes from this message.

        Matches Instagram (6 digits), Facebook (5-8 digits), and generic
        alphanumeric tokens.
        """
        codes = []
        # IG / FB numeric codes
        for m in re.finditer(r"\b(\d{5,8})\b", self.body):
            codes.append(m.group(1))
        # Alphanumeric tokens (rare for IG/FB but kept for completeness)
        for m in re.finditer(r"\b([A-Z0-9]{6,10})\b", self.body):
            codes.append(m.group(1))
        # Common phrasings: "your code is 123456", "code: 123456"
        for m in re.finditer(r"(?:code|confirmation|verify)[^\d]{0,20}(\d{4,8})",
                             self.body, re.IGNORECASE):
            codes.append(m.group(1))
        return codes

    def to_dict(self) -> dict:
        d = asdict(self)
        d["codes"] = self.extract_codes()
        return d


class Mailbox(ABC):
    """Abstract base. Each backend owns one disposable address."""

    @abstractmethod
    def get_address(self) -> str:
        """Return the disposable email address for this mailbox."""

    @abstractmethod
    def fetch_messages(self, since_id: Optional[str] = None) -> list[InboxMessage]:
        """Return all messages currently in the inbox (or since the given id)."""

    @abstractmethod
    def backend_name(self) -> str:
        """Identifier for debugging: 'guerrillamail', 'emailfake', 'console'."""


# ---- GuerrillaMail ----

class GuerrillaMailBackend(Mailbox):
    """JSON API backend. Docs: https://www.guerrillamail.com/GuerrillaMailAPI/"""

    BASE = "https://api.guerrillamail.com/ajax.php"

    def __init__(self):
        self.email_addr: Optional[str] = None
        self.sid_token: Optional[str] = None

    def _init_session(self) -> None:
        if self.email_addr is not None:
            return
        import requests
        r = requests.get(self.BASE, params={"f": "get_email_address"}, timeout=15)
        r.raise_for_status()
        data = r.json()
        self.email_addr = data["email_addr"]
        self.sid_token = data["sid_token"]

    def get_address(self) -> str:
        self._init_session()
        return self.email_addr

    def fetch_messages(self, since_id: Optional[str] = None) -> list[InboxMessage]:
        self._init_session()
        import requests
        r = requests.get(self.BASE,
                         params={"f": "get_email_list", "offset": 0,
                                 "sid_token": self.sid_token},
                         timeout=15)
        r.raise_for_status()
        data = r.json()
        out = []
        for msg in data.get("list", []):
            mid = str(msg.get("mail_id", ""))
            if since_id is not None and mid <= since_id:
                continue
            # Fetch full body for the codes to be visible
            try:
                r2 = requests.get(self.BASE,
                                  params={"f": "fetch_message",
                                          "email_id": mid,
                                          "sid_token": self.sid_token},
                                  timeout=15)
                body_data = r2.json()
                full_body = body_data.get("mail_body", msg.get("mail_excerpt", ""))
            except Exception:
                full_body = msg.get("mail_excerpt", "")
            out.append(InboxMessage(
                sender=msg.get("mail_from", ""),
                subject=msg.get("mail_subject", ""),
                body=full_body,
                received_at=float(msg.get("mail_timestamp", time.time())),
                message_id=mid,
                raw=msg,
            ))
        return out

    def backend_name(self) -> str:
        return "guerrillamail"


# ---- Email-fake (legacy, often broken) ----

class EmailFakeBackend(Mailbox):
    """Scrapes email-fake.com. Frequently returns empty/error responses."""

    BASE = "https://email-fake.com/"

    def __init__(self):
        self.email_addr: Optional[str] = None
        self.mail_name: Optional[str] = None
        self.domain: Optional[str] = None

    def get_address(self) -> str:
        if self.email_addr is not None:
            return self.email_addr
        import requests
        from bs4 import BeautifulSoup
        r = requests.get(self.BASE, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "html.parser")
        el = soup.find("span", {"id": "email_ch_text"})
        if not el or not el.contents:
            raise RuntimeError(
                "email-fake.com returned no email element. The site is often "
                "broken or behind Cloudflare. Use GuerrillaMailBackend instead."
            )
        email = el.contents[0]
        if not isinstance(email, str):
            email = str(email)
        self.email_addr = email
        if "@" in email:
            self.mail_name, self.domain = email.split("@", 1)
        return self.email_addr

    def fetch_messages(self, since_id: Optional[str] = None) -> list[InboxMessage]:
        if not self.email_addr:
            self.get_address()
        import requests
        from bs4 import BeautifulSoup
        url = f"{self.BASE}{self.domain}/{self.mail_name}"
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "html.parser")
        out = []
        # email-fake's inbox is in an HTML table; the message id is the row id
        rows = soup.select("table tr") or soup.select("#email-table tr")
        for i, row in enumerate(rows):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            subject = cells[0].get_text(strip=True)
            excerpt = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            mid = row.get("id") or str(i)
            if since_id is not None and mid <= since_id:
                continue
            out.append(InboxMessage(
                sender="unknown",
                subject=subject,
                body=excerpt,
                received_at=time.time(),
                message_id=mid,
                raw={"html": str(row)[:500]},
            ))
        return out

    def backend_name(self) -> str:
        return "emailfake"


# ---- Console (for testing/observe-only) ----

class ConsoleBackend(Mailbox):
    """Returns a placeholder email. Never receives mail — for debugging flows only."""

    def __init__(self, address: str = "observe@example.com"):
        self.email_addr = address
        self._received: list[InboxMessage] = []

    def get_address(self) -> str:
        return self.email_addr

    def fetch_messages(self, since_id: Optional[str] = None) -> list[InboxMessage]:
        return list(self._received)

    def inject_message(self, sender: str, subject: str, body: str) -> None:
        """For testing — manually inject a 'received' message."""
        self._received.append(InboxMessage(
            sender=sender, subject=subject, body=body,
            received_at=time.time(), message_id=str(len(self._received)),
        ))

    def backend_name(self) -> str:
        return "console"


def make_mailbox(backend: str = "guerrillamail") -> Mailbox:
    """Factory."""
    backends = {
        "guerrillamail": GuerrillaMailBackend,
        "emailfake": EmailFakeBackend,
        "console": ConsoleBackend,
    }
    if backend not in backends:
        raise ValueError(f"Unknown backend '{backend}'. Available: {list(backends)}")
    return backends[backend]()


def wait_for_code(mailbox: Mailbox,
                  sender_filter: Optional[str] = None,
                  timeout_seconds: int = 180,
                  poll_interval: float = 3.0,
                  progress_callback=None) -> Optional[InboxMessage]:
    """Poll mailbox until a message arrives matching the filter.

    Returns the message, or None on timeout.

    sender_filter: e.g. "instagram" or "facebook" (case-insensitive substring)
    progress_callback: optional callable(dict) for status updates
    """
    deadline = time.time() + timeout_seconds
    last_id_seen = None
    seen_message_ids = set()
    while time.time() < deadline:
        try:
            msgs = mailbox.fetch_messages(since_id=last_id_seen)
        except Exception as e:
            if progress_callback:
                progress_callback({"event": "poll_error", "error": str(e),
                                   "backend": mailbox.backend_name()})
            time.sleep(poll_interval)
            continue
        for m in msgs:
            if m.message_id in seen_message_ids:
                continue
            seen_message_ids.add(m.message_id)
            if sender_filter and sender_filter.lower() not in (m.sender + m.subject + m.body).lower():
                continue
            if progress_callback:
                progress_callback({
                    "event": "message_received",
                    "backend": mailbox.backend_name(),
                    "sender": m.sender,
                    "subject": m.subject,
                    "codes": m.extract_codes(),
                    "message_id": m.message_id,
                })
            return m
        last_id_seen = max((m.message_id for m in msgs), default=last_id_seen)
        if progress_callback:
            progress_callback({
                "event": "poll_tick",
                "backend": mailbox.backend_name(),
                "elapsed": int(deadline - time.time()),
                "address": mailbox.get_address(),
            })
        time.sleep(poll_interval)
    return None