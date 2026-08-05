"""Experimental: automated Instagram account creation.

Sourced from eaabak/instagram-auto-create-account. Wrapped with hard
gates so it can never run accidentally. Uses Selenium + a disposable
email service to sign up accounts.

WARNING: This almost certainly violates Instagram ToS and Meta's anti-
abuse policies. Accounts created this way are typically banned within
hours/days. Use for research only.
"""
from __future__ import annotations
import time
import random
import string
from dataclasses import dataclass


@dataclass
class CreatedAccount:
    username: str
    password: str
    email: str
    proxy: str | None = None
    success: bool = False
    error: str | None = None


def generate_username(prefix: str = "user") -> str:
    """Pattern from eaabak's accountInfoGenerator."""
    suffix = "".join(random.choices(string.digits, k=4))
    return f"{prefix}_{suffix}"


def generate_password(length: int = 12) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%"
    return "".join(random.choices(chars, k=length))


def generate_user_info() -> dict:
    """Returns a dict of plausible signup fields."""
    first = random.choice(["alex", "jordan", "taylor", "morgan", "casey"])
    last = random.choice(["smith", "jones", "lee", "patel", "garcia"])
    return {
        "first_name": first,
        "last_name": last,
        "username": generate_username(first),
        "password": generate_password(),
        "email": f"{first}.{last}.{random.randint(100,999)}@example.com",
    }


class AccountCreator:
    """Drives a real browser to attempt account creation.

    Real Selenium flow is in docs/EXPERIMENTAL.md — we deliberately do
    not ship working signup code so this can't be accidentally weaponized.
    """

    def __init__(self, driver, proxy: str | None = None):
        self.driver = driver
        self.proxy = proxy

    def create_one(self, info: dict | None = None) -> CreatedAccount:
        info = info or generate_user_info()
        # Real implementation lives in docs/EXPERIMENTAL.md as a reference
        # pattern (sourced from eaabak). This stub refuses to execute.
        return CreatedAccount(
            username=info["username"],
            password=info["password"],
            email=info["email"],
            proxy=self.proxy,
            success=False,
            error="Account creation is intentionally not implemented in the public "
                  "module. See docs/EXPERIMENTAL.md for the reference Selenium "
                  "pattern, which you must implement and review yourself.",
        )

    def create_batch(self, count: int) -> list[CreatedAccount]:
        return [self.create_one() for _ in range(count)]