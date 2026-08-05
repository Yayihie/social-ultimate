"""Gating for experimental automation features.

These features are documented as unstable / against Instagram ToS in
README. They will refuse to operate unless:
  1. EXPERIMENTAL_ENABLED=true in env
  2. User explicitly opted in (consent record stored)
"""
import inspect
from functools import wraps
from fastapi import HTTPException, status

from app.core.config import settings


def experimental_endpoint():
    """Decorator: endpoint only available if experimental module is enabled.

    Handles both sync and async endpoints.
    """
    def decorator(fn):
        @wraps(fn)
        async def async_wrapper(*args, **kwargs):
            if not settings.experimental_enabled:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Experimental module disabled. Set EXPERIMENTAL_ENABLED=true "
                        "in .env. WARNING: these features violate Instagram ToS — "
                        "use at your own risk."
                    ),
                )
            result = fn(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

        @wraps(fn)
        def sync_wrapper(*args, **kwargs):
            if not settings.experimental_enabled:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Experimental module disabled. Set EXPERIMENTAL_ENABLED=true "
                        "in .env. WARNING: these features violate Instagram ToS — "
                        "use at your own risk."
                    ),
                )
            return fn(*args, **kwargs)

        return async_wrapper if inspect.iscoroutinefunction(fn) else sync_wrapper
    return decorator


def require_explicit_consent(user_consented: bool) -> None:
    """User must have explicitly ticked a consent box to run experimental jobs."""
    if settings.experimental_require_explicit_opt_in and not user_consented:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Explicit consent required. Pass consent_acknowledged=true. "
                "This confirms you understand these automation features violate "
                "Instagram Terms of Service and may result in account suspension."
            ),
        )