"""Facebook account creator.

Approach:
  Selenium drives facebook.com/r.php through the mobile signup flow
  (m.facebook.com/reg/), which is friendlier to automation than the
  desktop flow and requires fewer anti-bot hurdles.

  Facebook does not require email confirmation on signup (unlike IG).
  It does require:
    - name (first/last)
    - email or phone (we use disposable email)
    - password
    - birthday
    - gender

Flow:
  1. Open m.facebook.com/reg/
  2. Fill name, email, password
  3. Fill birthday, select gender
  4. Submit
  5. Capture any post-signup verification step (email/SMS)
  6. Save cookies for later session

Gated by EXPERIMENTAL_ENABLED + consent_acknowledged.
"""
from __future__ import annotations
import re
import time
import pickle
import random
from dataclasses import dataclass
from typing import Optional

from app.experimental.driver_utils import (
    DriverOptions, make_driver, random_first_name, random_last_name,
    random_password, random_birthday, human_delay, safe_send,
)
from app.experimental.mailbox import make_mailbox, Mailbox


SIGNUP_URL = "https://m.facebook.com/reg/"


@dataclass
class CreatedFacebookAccount:
    first_name: str
    last_name: str
    email: str
    password: str
    birthday: str
    gender: str
    proxy: Optional[str] = None
    success: bool = False
    error: Optional[str] = None
    cookies_file: Optional[str] = None
    fbid: Optional[str] = None
    mailbox_backend: str = ""
    mailbox_address: str = ""


@dataclass
class FacebookCreateResult:
    account: CreatedFacebookAccount
    driver: object
    mailbox: Optional[Mailbox] = None


def create_facebook_account(
    user_id: int,
    db_url: str,
    driver_options: Optional[DriverOptions] = None,
    headless: bool = True,
    proxy: Optional[str] = None,
    gender: Optional[str] = None,  # "male" / "female" — random if None
    mailbox_backend: str = "guerrillamail",
) -> FacebookCreateResult:
    """Create one Facebook account via mobile signup flow."""
    opts = driver_options or DriverOptions(headless=headless, proxy=proxy)
    driver = make_driver(opts)
    mailbox = make_mailbox(mailbox_backend)
    info = {
        "first_name": random_first_name(),
        "last_name": random_last_name(),
        "password": random_password(12),
        "birthday": "",  # filled after
        "gender": gender or random.choice(["1", "2"]),  # 1=female, 2=male in FB form
    }

    def _fail(error: str) -> FacebookCreateResult:
        return FacebookCreateResult(
            account=CreatedFacebookAccount(
                first_name=info["first_name"],
                last_name=info["last_name"],
                email=info.get("email", ""),
                password=info["password"],
                birthday=info["birthday"],
                gender=info["gender"],
                proxy=opts.proxy,
                success=False,
                error=error,
                mailbox_backend=mailbox.backend_name(),
                mailbox_address=info.get("email", ""),
            ),
            driver=driver,
            mailbox=mailbox,
        )

    try:
        info["email"] = mailbox.get_address()
    except Exception as e:
        return _fail(str(e))

    year, month, day = random_birthday(min_year=1988, max_year=2003)
    info["birthday"] = f"{month:02d}/{day:02d}/{year}"

    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait, Select
        from selenium.webdriver.support import expected_conditions as EC

        driver.get(SIGNUP_URL)
        human_delay(3.0, 5.0)

        # The mobile signup form uses input[name=...] for these fields.
        def _by_name(name: str, timeout: int = 20):
            return WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.NAME, name))
            )

        # 1. First name
        try:
            fn = _by_name("firstname")
            safe_send(fn, info["first_name"])
            human_delay(0.3, 0.7)
        except Exception as e:
            return _fail(f"firstname field not found: {e}")

        # 2. Last name
        try:
            ln = _by_name("lastname")
            safe_send(ln, info["last_name"])
            human_delay(0.3, 0.7)
        except Exception as e:
            return _fail(f"lastname field not found: {e}")

        # 3. Email
        try:
            em = _by_name("reg_email__")
            safe_send(em, info["email"])
            human_delay(0.3, 0.7)
        except Exception as e:
            # Some flows name it reg_email
            try:
                em = _by_name("reg_email")
                safe_send(em, info["email"])
            except Exception as e2:
                return _fail(f"email field not found: {e2}")

        # 4. Re-enter email (FB requires confirmation on mobile)
        try:
            em2 = _by_name("reg_email_confirmation__")
            safe_send(em2, info["email"])
            human_delay(0.3, 0.7)
        except Exception:
            try:
                em2 = _by_name("reg_email_confirmation")
                safe_send(em2, info["email"])
            except Exception:
                pass  # not always present

        # 5. Password
        try:
            pw = _by_name("reg_passwd__")
            safe_send(pw, info["password"])
            human_delay(0.3, 0.7)
        except Exception as e:
            return _fail(f"password field not found: {e}")

        # 6. Birthday — three selects (day, month, year)
        try:
            Select(_by_name("birthday_day")).select_by_value(f"{day}")
            human_delay(0.2, 0.5)
            Select(_by_name("birthday_month")).select_by_value(f"{month}")
            human_delay(0.2, 0.5)
            Select(_by_name("birthday_year")).select_by_value(f"{year}")
            human_delay(0.4, 0.8)
        except Exception as e:
            return _fail(f"birthday select fields not found: {e}")

        # 7. Gender — radio buttons named 'sex'
        try:
            radios = driver.find_elements(By.NAME, "sex")
            if radios:
                # radios: [female, male] typically — index from gender code
                idx = int(info["gender"]) - 1
                if 0 <= idx < len(radios):
                    radios[idx].click()
                    human_delay(0.3, 0.6)
        except Exception as e:
            return _fail(f"gender radio not found: {e}")

        # 8. Submit
        submitted = False
        for xp in [
            "//button[@name='websubmit']",
            "//button[@type='submit']",
            "//input[@type='submit']",
            "//button[contains(., 'Sign Up')]",
        ]:
            try:
                WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, xp))).click()
                submitted = True
                break
            except Exception:
                continue
        if not submitted:
            return _fail("Submit button not found — FB flow may have changed")
        human_delay(5.0, 8.0)

        # 9. Check for checkpoint (phone/email confirmation, captcha)
        current_url = driver.current_url
        fbid = None
        # Try to extract fb id from URL or cookies
        try:
            cookies = driver.get_cookies()
            for c in cookies:
                if c.get("name") == "c_user":
                    fbid = c.get("value")
                    break
        except Exception:
            pass

        # 10. Save cookies
        cookies_file = f"/tmp/fb_cookies_{info['first_name']}_{fbid or 'unknown'}.pkl"
        try:
            with open(cookies_file, "wb") as f:
                pickle.dump(driver.get_cookies(), f)
        except Exception:
            cookies_file = None

        # If we got a checkpoint page (often happens), mark success=False with info
        if "checkpoint" in current_url.lower() or "confirm" in current_url.lower():
            return FacebookCreateResult(
                account=CreatedFacebookAccount(
                    first_name=info["first_name"],
                    last_name=info["last_name"],
                    email=info["email"],
                    password=info["password"],
                    birthday=info["birthday"],
                    gender=info["gender"],
                    proxy=opts.proxy,
                    success=False,
                    error=f"Account created but reached security checkpoint: {current_url}. "
                          "Manual intervention required (phone/photo verification).",
                    cookies_file=cookies_file,
                    fbid=fbid,
                ),
                driver=driver,
            )

        return FacebookCreateResult(
            account=CreatedFacebookAccount(
                first_name=info["first_name"],
                last_name=info["last_name"],
                email=info["email"],
                password=info["password"],
                birthday=info["birthday"],
                gender=info["gender"],
                proxy=opts.proxy,
                success=True,
                error=None,
                cookies_file=cookies_file,
                fbid=fbid,
            ),
            driver=driver,
        )

    except Exception as e:
        return _fail(f"Unexpected error: {e}")


def create_batch(count: int, user_id: int, db_url: str, **kwargs) -> list[FacebookCreateResult]:
    """Create multiple Facebook accounts sequentially."""
    results = []
    for _ in range(count):
        result = create_facebook_account(user_id=user_id, db_url=db_url, **kwargs)
        results.append(result)
        try:
            result.driver.quit()
        except Exception:
            pass
    return results