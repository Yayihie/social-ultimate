"""DEPRECATED stub. The real creator implementations live in:
  - app.experimental.instagram_creator  (Instagram)
  - app.experimental.facebook_creator   (Facebook via mobile signup)

This module is kept only for backward compatibility with the original
test imports. Do not use it for new code.
"""
from app.experimental.instagram_creator import (  # noqa: F401
    CreatedAccount, CreateResult, create_instagram_account, create_batch,
)
from app.experimental.driver_utils import (  # noqa: F401
    generate_username as _gen_username,
    generate_password as _gen_password,
)
import random
import string


def generate_username(prefix: str = "user") -> str:
    return _gen_username(prefix)


def generate_password(length: int = 12) -> str:
    return _gen_password(length)


def generate_user_info() -> dict:
    from app.experimental.driver_utils import (
        random_full_name, random_username, random_password,
    )
    return {
        "first_name": random_full_name().split()[0],
        "last_name": random_full_name().split()[-1],
        "username": random_username(),
        "password": random_password(),
        "email": f"{random_username()}@example.com",
    }


# Old class kept for backward compat — delegates to the new creator.
from app.experimental.instagram_creator import create_instagram_account as _create_ig


class AccountCreator:
    """Backward-compat wrapper. New code should call
    app.experimental.instagram_creator.create_instagram_account or
    app.experimental.facebook_creator.create_facebook_account directly."""

    def __init__(self, driver, proxy: str | None = None):
        self.driver = driver
        self.proxy = proxy

    def create_one(self, info=None):
        from app.experimental.instagram_creator import CreatedAccount as CA
        return CA(
            username=info["username"] if info else "unknown",
            password=info["password"] if info else "unknown",
            email=info["email"] if info else "unknown",
            full_name=info.get("full_name", "") if info else "",
            proxy=self.proxy,
            success=False,
            error=(
                "AccountCreator.create_one() is deprecated. Use "
                "app.experimental.instagram_creator.create_instagram_account() "
                "or app.experimental.facebook_creator.create_facebook_account() "
                "directly. This wrapper does not run a real driver."
            ),
        )

    def create_batch(self, count: int):
        return [self.create_one() for _ in range(count)]