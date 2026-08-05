"""Instagram account creator.

Ported from eaabak/instagram-auto-create-account. Uses Selenium + a
disposable email service to drive instagram.com/accounts/emailsignup.

Flow:
  1. Open signup page
  2. Generate plausible identity (name, username, password)
  3. Fill email/fullname/username/password fields
  4. Submit form
  5. Fill birthday (required step)
  6. Poll disposable inbox for verification code
  7. Enter code
  8. Save credentials to CreatedAccount

This module is gated by EXPERIMENTAL_ENABLED + consent_acknowledged.
"""
from __future__ import annotations
import re
import time
import random
from dataclasses import dataclass, field
from typing import Optional

from app.experimental.driver_utils import (
    DriverOptions, make_driver, random_full_name, random_username,
    random_password, random_birthday, human_delay, safe_send,
)


SIGNUP_URL = "https://www.instagram.com/accounts/emailsignup/"
INBOX_URL_BASE = "https://email-fake.com/"


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


@dataclass
class CreateResult:
    account: CreatedAccount
    driver: object  # the selenium driver in its final state (caller closes)


def _get_fake_email() -> str:
    """Fetch a disposable email from email-fake.com.

    Returns the email string, or raises RuntimeError if the service is down.
    """
    import requests
    from bs4 import BeautifulSoup
    try:
        r = requests.get(INBOX_URL_BASE, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "html.parser")
        mail_el = soup.find("span", {"id": "email_ch_text"})
        if not mail_el or not mail_el.contents:
            raise RuntimeError("email-fake.com returned no email element")
        # contents is e.g. ['foo123@bar.com']
        email = mail_el.contents[0]
        if not isinstance(email, str):
            email = str(email)
        return email
    except Exception as e:
        raise RuntimeError(f"Could not get disposable email: {e}") from e


def _wait_for_instagram_code(mail_name: str, domain: str, driver, timeout: int = 180) -> str:
    """Open the inbox in a new tab, poll for an Instagram confirmation code."""
    inbox_url = f"{INBOX_URL_BASE}{domain}/{mail_name}"
    driver.execute_script("window.open('');")
    driver.switch_to.window(driver.window_handles[-1])
    driver.get(inbox_url)
    human_delay(1.0, 2.0)
    deadline = time.time() + timeout
    code = ""
    while time.time() < deadline:
        title = driver.title or ""
        # email-fake.com sets the title to the email subject; the IG code is in it
        m = re.search(r"\b(\d{6})\b", title)
        if m:
            code = m.group(1)
            break
        driver.refresh()
        human_delay(1.5, 3.0)
    driver.close()
    driver.switch_to.window(driver.window_handles[0])
    if not code:
        raise RuntimeError(f"Timed out after {timeout}s waiting for Instagram code in {mail_name}@{domain}")
    return code


def create_instagram_account(
    driver_options: Optional[DriverOptions] = None,
    headless: bool = True,
    proxy: Optional[str] = None,
) -> CreateResult:
    """Create one Instagram account. Returns CreateResult; caller closes driver.

    driver_options: pass a pre-configured DriverOptions for full control,
        or leave None to use defaults (headless + your settings.proxy).
    headless: shorthand override for non-headless run.
    proxy: shorthand override for proxy URL.
    """
    opts = driver_options or DriverOptions(headless=headless, proxy=proxy)
    driver = make_driver(opts)
    info = {
        "email": "",
        "full_name": random_full_name(),
        "username": random_username(),
        "password": random_password(),
    }

    def _fail(error: str) -> CreateResult:
        return CreateResult(
            account=CreatedAccount(
                username=info["username"],
                password=info["password"],
                email=info.get("email", ""),
                full_name=info["full_name"],
                proxy=opts.proxy,
                success=False,
                error=error,
            ),
            driver=driver,
        )

    try:
        # 1. Get disposable email
        info["email"] = _get_fake_email()
    except Exception as e:
        return _fail(str(e))

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
        from selenium.webdriver.support.ui import WebDriverWait
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

        # 7. Submit — try common selectors (Instagram rotates these)
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
            return _fail("Could not click Sign up button (all selectors failed)")
        human_delay(4.0, 6.0)

        # 8. Birthday dropdowns (Instagram now requires this)
        year, month, day = random_birthday()
        try:
            selects = driver.find_elements(By.TAG_NAME, "select")
            if len(selects) >= 3:
                from selenium.webdriver.support.ui import Select
                Select(selects[0]).select_by_value(str(month))
                human_delay(0.3, 0.6)
                Select(selects[1]).select_by_value(str(day))
                human_delay(0.3, 0.6)
                Select(selects[2]).select_by_value(str(year))
                human_delay(0.4, 0.8)
                # Submit
                for xp in [
                    "//*[@id='react-root']/section/main/div/div/div[1]/div/div[6]/button",
                    "//button[@type='submit']",
                    "//div[@role='button'][contains(., 'Next')]",
                ]:
                    try:
                        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, xp))).click()
                        break
                    except Exception:
                        continue
                human_delay(3.0, 5.0)
            else:
                return _fail("Birthday select dropdowns not found — Instagram flow may have changed")
        except Exception as e:
            return _fail(f"Birthday step failed: {e}")

        # 9. Wait for verification code email
        try:
            mail_name, domain = info["email"].split("@")
        except ValueError:
            return _fail(f"Bad email format: {info['email']}")

        try:
            code = _wait_for_instagram_code(mail_name, domain, driver, timeout=180)
        except Exception as e:
            return _fail(str(e))

        # 10. Enter the code
        try:
            code_field = _find("email_confirmation_code", timeout=15)
            safe_send(code_field, code)
            human_delay(0.5, 1.0)
            from selenium.webdriver.common.keys import Keys
            code_field.send_keys(Keys.ENTER)
        except Exception as e:
            return _fail(f"Could not enter verification code: {e}")

        human_delay(3.0, 5.0)

        # 11. Save cookies for later login
        cookies_file = f"/tmp/ig_cookies_{info['username']}.pkl"
        try:
            import pickle
            with open(cookies_file, "wb") as f:
                pickle.dump(driver.get_cookies(), f)
        except Exception:
            cookies_file = None

        return CreateResult(
            account=CreatedAccount(
                username=info["username"],
                password=info["password"],
                email=info["email"],
                full_name=info["full_name"],
                proxy=opts.proxy,
                success=True,
                error=None,
                cookies_file=cookies_file,
            ),
            driver=driver,
        )

    except Exception as e:
        return _fail(f"Unexpected error: {e}")


def create_batch(count: int, **kwargs) -> list[CreateResult]:
    """Create multiple accounts sequentially. Each account uses its own driver.

    WARNING: Creates `count` separate Chrome browser sessions. Use sparingly.
    """
    results = []
    for _ in range(count):
        result = create_instagram_account(**kwargs)
        results.append(result)
        try:
            result.driver.quit()
        except Exception:
            pass
    return results