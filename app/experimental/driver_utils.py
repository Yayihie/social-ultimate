"""Shared Selenium driver factory + stealth helpers for account creators.

Provides a configured Chrome driver with options tuned for *not* being
immediately flagged as a bot:
- random realistic User-Agent
- disabled navigator.webdriver flag
- realistic window size
- optional proxy

NOTE: These mitigations reduce detection, they don't eliminate it.
Both Instagram and Facebook will still flag accounts created this way
within hours/days. Use only for legitimate testing/QA on accounts you
own or have explicit permission to create.
"""
from __future__ import annotations
import random
import string
from typing import Optional
from dataclasses import dataclass


_DESKTOP_UAS = [
    # Chrome on macOS / Windows / Linux — recent stable versions
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
]


_FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Avery", "Quinn",
    "Rowan", "Sage", "River", "Skyler", "Reese", "Cameron", "Drew", "Hayden",
    "Parker", "Emerson", "Finley", "Logan", "Blake", "Charlie", "Dakota",
    "Elliot", "Frankie", "Harper", "Indigo", "Jamie", "Kendall", "Lane",
    "Marlowe", "Noah", "Oakley", "Phoenix", "Remy", "Sawyer", "Tatum",
    "Wren", "Zion",
]
_LAST_NAMES = [
    "Smith", "Jones", "Lee", "Patel", "Garcia", "Johnson", "Brown", "Davis",
    "Miller", "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Jackson",
    "White", "Harris", "Martin", "Thompson", "Robinson", "Clark", "Lewis",
    "Walker", "Hall", "Allen", "Young", "King", "Wright", "Scott", "Green",
]


@dataclass
class DriverOptions:
    headless: bool = True
    proxy: Optional[str] = None
    user_agent: Optional[str] = None
    window_width: int = 1366
    window_height: int = 768
    chromedriver_path: Optional[str] = None


def make_driver(options: DriverOptions):
    """Build a configured Selenium Chrome driver.

    Raises RuntimeError with a helpful message if selenium/chromedriver
    aren't installed — never silently produces a broken driver.
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
    except ImportError as e:
        raise RuntimeError(
            "Selenium is not installed. pip install -r requirements.txt (or "
            "pip install selenium) and ensure chromedriver is on PATH or "
            "set CHROMEDRIVER_PATH in .env."
        ) from e

    chrome_opts = Options()
    if options.headless:
        chrome_opts.add_argument("--headless=new")
    chrome_opts.add_argument(f"--window-size={options.window_width},{options.window_height}")
    chrome_opts.add_argument("--disable-blink-features=AutomationControlled")
    chrome_opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_opts.add_experimental_option("useAutomationExtension", False)
    chrome_opts.add_argument("--disable-infobars")
    chrome_opts.add_argument("--disable-notifications")
    chrome_opts.add_argument("--no-sandbox")
    chrome_opts.add_argument("--disable-dev-shm-usage")
    chrome_opts.add_argument("--lang=en-US,en;q=0.9")

    ua = options.user_agent or random.choice(_DESKTOP_UAS)
    chrome_opts.add_argument(f"--user-agent={ua}")

    if options.proxy:
        chrome_opts.add_argument(f"--proxy-server={options.proxy}")

    service_kwargs = {}
    if options.chromedriver_path:
        service_kwargs["executable_path"] = options.chromedriver_path
    service = Service(**service_kwargs) if service_kwargs else Service()

    driver = webdriver.Chrome(service=service, options=chrome_opts)
    # Stealth: hide webdriver flag
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"},
    )
    driver.set_page_load_timeout(60)
    return driver


# ---- Identity generation helpers used by both IG and FB creators ----

def random_first_name() -> str:
    return random.choice(_FIRST_NAMES)


def random_last_name() -> str:
    return random.choice(_LAST_NAMES)


def random_full_name() -> str:
    return f"{random_first_name()} {random_last_name()}"


def random_username(prefix: str = "user", length: int = 8) -> str:
    """Generate a plausible username. e.g. 'taylor_4827'."""
    base = random.choice(_FIRST_NAMES).lower()
    suffix = "".join(random.choices(string.digits, k=length - len(base) - 1))
    return f"{base}_{suffix}"


# Backward-compat aliases for older code (eaabak-style API surface)
def generate_username(prefix: str = "user") -> str:
    return random_username(prefix)


def random_password(length: int = 14) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%&*"
    return "".join(random.choices(chars, k=length))


def generate_password(length: int = 14) -> str:
    return random_password(length)


def random_birthday(min_year: int = 1985, max_year: int = 2002) -> tuple[int, int, int]:
    year = random.randint(min_year, max_year)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return year, month, day


def human_delay(min_s: float = 0.6, max_s: float = 2.4) -> None:
    """Sleep for a random 'human-like' interval."""
    import time
    time.sleep(random.uniform(min_s, max_s))


def safe_send(element, text: str) -> None:
    """Type a value with realistic per-character delays."""
    for ch in text:
        element.send_keys(ch)
        # Tiny delay, faster than human typing but not instant
        import time
        time.sleep(random.uniform(0.03, 0.12))