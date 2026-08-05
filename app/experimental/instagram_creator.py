"""Instagram account creator.

Ported from eaabak/instagram-auto-create-account. Uses Selenium +
a disposable email service (default: GuerrillaMail JSON API).

Flow:
  1. Acquire a disposable mailbox (GuerrillaMail by default)
  2. Open instagram.com/accounts/emailsignup/
  3. Fill email/fullname/username/password fields
  4. Submit form
  5. Fill birthday (required step)
  6. Poll mailbox for Instagram's confirmation code (saved to DB)
  7. Enter code
  8. Save cookies + credentials to CreatedAccount

Every step emits a progress event. Polling ticks and any received
message are persisted to the InboxSnapshot table so you can see
exactly what code arrived (or didn't).
"""
from __future__ import annotations
import time
import pickle
import random
from dataclasses import dataclass
from typing import Optional

from app.experimental.driver_utils import (
    DriverOptions, make_driver, random_full_name, random_username,
    random_password, random_birthday, human_delay, safe_send,
)
from app.experimental.mailbox import (
    Mailbox, make_mailbox, wait_for_code, InboxMessage,
)


SIGNUP_URL = "https://www.instagram.com/accounts/emailsignup/"


@dataclass
class CreatedAccount:
    username: str
    password: str
    email: str
    full_name: str
    proxy: Optional[str] = None
    success: bool = False
    error: Optional[str] = None
    cookies_file: Optional[str] = None
    mailbox_backend: str = ""
    mailbox_address: str = ""
    extracted_codes: list = None  # what codes we saw in the inbox
    inbox_message_id: Optional[str] = None

    def __post_init__(self):
        if self.extracted_codes is None:
            self.extracted_codes = []


@dataclass
class CreateResult:
    account: CreatedAccount
    driver: object
    mailbox: Optional[Mailbox] = None


def _capture_inbox_snapshot(
    db, user_id: int, account_record_id: Optional[int],
    mailbox: Mailbox, message: InboxMessage,
) -> None:
    """Persist an inbox message + extracted codes to the InboxSnapshot table."""
    from app.db.models import InboxSnapshot
    snap = InboxSnapshot(
        user_id=user_id,
        account_record_id=account_record_id,
        backend=mailbox.backend_name(),
        email_address=mailbox.get_address(),
        sender=message.sender,
        subject=message.subject,
        body_excerpt=message.body[:500] if message.body else "",
        body_full=message.body or "",
        extracted_codes=message.extract_codes(),
        message_id=message.message_id,
        event="message_received",
    )
    db.add(snap)
    db.commit()


def _capture_poll_tick(db, user_id: int, account_record_id: Optional[int],
                       mailbox: Mailbox, event: str = "poll_tick",
                       error: Optional[str] = None) -> None:
    """Persist a polling tick (with no message) for debugging."""
    from app.db.models import InboxSnapshot
    snap = InboxSnapshot(
        user_id=user_id,
        account_record_id=account_record_id,
        backend=mailbox.backend_name(),
        email_address=mailbox.get_address(),
        event=event,
        body_excerpt=error,
    )
    db.add(snap)
    db.commit()


def create_instagram_account(
    user_id: int,
    db_url: str,
    driver_options: Optional[DriverOptions] = None,
    headless: bool = True,
    proxy: Optional[str] = None,
    mailbox_backend: str = "guerrillamail",
    verification_timeout: int = 180,
) -> CreateResult:
    """Create one Instagram account. Caller is responsible for closing driver.

    user_id / db_url: passed in so we can persist inbox snapshots during polling.
    mailbox_backend: "guerrillamail" (default), "emailfake", or "console".
    verification_timeout: seconds to wait for the Instagram code email.
    """
    from app.db.session import SessionLocal

    opts = driver_options or DriverOptions(headless=headless, proxy=proxy)
    driver = make_driver(opts)
    mailbox = make_mailbox(mailbox_backend)
    db = SessionLocal()

    info = {
        "email": "",
        "full_name": random_full_name(),
        "username": random_username(),
        "password": random_password(),
    }

    def _fail(error: str, captured_codes: list = None) -> CreateResult:
        if captured_codes is None:
            captured_codes = []
        return CreateResult(
            account=CreatedAccount(
                username=info["username"],
                password=info["password"],
                email=info.get("email", ""),
                full_name=info["full_name"],
                proxy=opts.proxy,
                success=False,
                error=error,
                mailbox_backend=mailbox.backend_name(),
                mailbox_address=info.get("email", ""),
                extracted_codes=captured_codes,
            ),
            driver=driver,
            mailbox=mailbox,
        )

    # 1. Acquire disposable email
    try:
        info["email"] = mailbox.get_address()
    except Exception as e:
        db.close()
        return _fail(f"Could not acquire email from {mailbox_backend}: {e}")

    # Create the CreatedAccountRecord up front so we can link inbox snapshots
    from app.db.models import CreatedAccountRecord
    rec = CreatedAccountRecord(
        user_id=user_id,
        platform="instagram",
        username=info["username"],
        email=info["email"],
        password=info["password"],
        full_name=info["full_name"],
        extra={"mailbox_backend": mailbox.backend_name(),
               "mailbox_address": info["email"]},
        success=False,
        error=None,
        proxy=opts.proxy,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    record_id = rec.id

    captured_codes: list[str] = []
    captured_message: Optional[InboxMessage] = None

    def _on_poll_event(payload: dict) -> None:
        nonlocal captured_message
        try:
            if payload.get("event") == "message_received":
                # We got a real email — fetch full message and persist
                msgs = mailbox.fetch_messages(since_id=None)
                msg = next((m for m in msgs
                            if m.message_id == payload.get("message_id")), None)
                if msg:
                    captured_codes.extend(msg.extract_codes())
                    captured_message = msg
                    _capture_inbox_snapshot(db, user_id, record_id, mailbox, msg)
            else:
                _capture_poll_tick(db, user_id, record_id, mailbox,
                                   event=payload.get("event", "poll_tick"),
                                   error=payload.get("error"))
        except Exception:
            pass  # never let DB writes kill the polling loop

    try:
        # 2. Open signup page
        driver.get(SIGNUP_URL)
        human_delay(3.0, 5.0)

        # Dismiss cookie banner if present
        try:
            cookie_btn = driver.find_element("xpath", "/html/body/div[3]/div/div/button[1]")
            cookie_btn.click()
            human_delay(0.5, 1.0)
        except Exception:
            pass

        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait, Select
        from selenium.webdriver.support import expected_conditions as EC

        def _find(name: str, timeout: int = 20):
            return WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.NAME, name))
            )

        # 3. Fill email
        email_field = _find("emailOrPhone")
        safe_send(email_field, info["email"])
        human_delay(0.4, 0.9)

        # 4. Full name
        fullname_field = _find("fullName")
        safe_send(fullname_field, info["full_name"])
        human_delay(0.4, 0.9)

        # 5. Username
        username_field = _find("username")
        safe_send(username_field, info["username"])
        human_delay(0.4, 0.9)

        # 6. Password
        password_field = _find("password")
        safe_send(password_field, info["password"])
        human_delay(0.6, 1.2)

        # 7. Submit
        submitted = False
        for xp in [
            "//*[@id='react-root']/section/main/div/div/div[1]/div/form/div[7]/div/button",
            "//button[@type='submit']",
            "//div[@role='button'][contains(., 'Sign up')]",
        ]:
            try:
                WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, xp))).click()
                submitted = True
                break
            except Exception:
                continue
        if not submitted:
            rec.error = "Could not click Sign up button"
            db.commit()
            return _fail(rec.error)
        human_delay(4.0, 6.0)

        # 8. Birthday dropdowns
        year, month, day = random_birthday()
        try:
            selects = driver.find_elements(By.TAG_NAME, "select")
            if len(selects) >= 3:
                Select(selects[0]).select_by_value(str(month))
                human_delay(0.3, 0.6)
                Select(selects[1]).select_by_value(str(day))
                human_delay(0.3, 0.6)
                Select(selects[2]).select_by_value(str(year))
                human_delay(0.4, 0.8)
                for xp in [
                    "//*[@id='react-root']/section/main/div/div/div[1]/div/div[6]/button",
                    "//button[@type='submit']",
                    "//div[@role='button'][contains(., 'Next')]",
                ]:
                    try:
                        WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, xp))).click()
                        break
                    except Exception:
                        continue
                human_delay(3.0, 5.0)
            else:
                rec.error = "Birthday selects not found (Instagram flow may have changed)"
                db.commit()
                return _fail(rec.error, captured_codes)
        except Exception as e:
            rec.error = f"Birthday step failed: {e}"
            db.commit()
            return _fail(rec.error, captured_codes)

        # 9. Poll mailbox for IG code
        try:
            msg = wait_for_code(
                mailbox,
                sender_filter="instagram",
                timeout_seconds=verification_timeout,
                poll_interval=4.0,
                progress_callback=_on_poll_event,
            )
        except Exception as e:
            rec.error = f"Mailbox polling crashed: {e}"
            db.commit()
            return _fail(rec.error, captured_codes)

        if msg is None:
            rec.error = (
                f"No Instagram email received after {verification_timeout}s. "
                f"Mailbox: {mailbox.get_address()} ({mailbox.backend_name()}). "
                f"Codes seen in any messages: {captured_codes or 'none'}."
            )
            db.commit()
            db.close()
            return _fail(rec.error, captured_codes)

        codes = msg.extract_codes()
        if not codes:
            rec.error = (
                f"Received Instagram email but no numeric code found. "
                f"Subject: {msg.subject!r}. Body excerpt: {msg.body[:200]!r}."
            )
            db.commit()
            db.close()
            return _fail(rec.error, captured_codes)

        code = codes[0]  # take the first plausible code

        # 10. Enter code
        try:
            code_field = _find("email_confirmation_code", timeout=15)
            safe_send(code_field, code)
            human_delay(0.5, 1.0)
            from selenium.webdriver.common.keys import Keys
            code_field.send_keys(Keys.ENTER)
        except Exception as e:
            rec.error = f"Could not enter code {code}: {e}"
            db.commit()
            db.close()
            return _fail(rec.error, captured_codes)

        human_delay(3.0, 5.0)

        # 11. Save cookies
        cookies_file = f"/tmp/ig_cookies_{info['username']}.pkl"
        try:
            with open(cookies_file, "wb") as f:
                pickle.dump(driver.get_cookies(), f)
        except Exception:
            cookies_file = None

        # Update record with success
        rec.success = True
        rec.extra = {
            **(rec.extra or {}),
            "cookies_file": cookies_file,
            "extracted_codes": codes,
            "code_used": code,
            "sender": msg.sender,
            "subject": msg.subject,
            "message_id": msg.message_id,
        }
        db.commit()
        db.close()

        return CreateResult(
            account=CreatedAccount(
                username=info["username"],
                password=info["password"],
                email=info["email"],
                full_name=info["full_name"],
                proxy=opts.proxy,
                success=True,
                cookies_file=cookies_file,
                mailbox_backend=mailbox.backend_name(),
                mailbox_address=info["email"],
                extracted_codes=codes,
                inbox_message_id=msg.message_id,
            ),
            driver=driver,
            mailbox=mailbox,
        )

    except Exception as e:
        try:
            rec.error = f"Unexpected error: {e}"
            db.commit()
        except Exception:
            pass
        db.close()
        return _fail(f"Unexpected error: {e}", captured_codes)


def create_batch(count: int, user_id: int, db_url: str, **kwargs) -> list[CreateResult]:
    """Create multiple accounts sequentially."""
    results = []
    for _ in range(count):
        result = create_instagram_account(user_id=user_id, db_url=db_url, **kwargs)
        results.append(result)
        try:
            result.driver.quit()
        except Exception:
            pass
    return results