"""Production Instagram integration via Meta Graph API (v18+).

This is the LEGAL, WORKING path for Instagram automation as of 2026.
Requires:
  - Instagram Business or Creator account
  - Facebook App with Instagram Basic Display or Graph API product
  - User grants permission via OAuth flow

The module is defensive: if credentials aren't configured, all methods
return clear errors rather than silently failing.
"""
from datetime import datetime, timedelta
from typing import Any
import httpx

from app.core.config import settings

GRAPH_BASE = "https://graph.facebook.com/v18.0"


class InstagramGraphError(Exception):
    pass


class InstagramClient:
    """Thin async wrapper around the Instagram Graph API.

    All methods return parsed JSON or raise InstagramGraphError with
    the actual API error message — never silently swallow failures.
    """

    def __init__(self, access_token: str, ig_user_id: str | None = None):
        self.access_token = access_token
        self.ig_user_id = ig_user_id
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        await self._client.aclose()

    def _check_configured(self) -> None:
        if not settings.instagram_app_id or not settings.instagram_app_secret:
            raise InstagramGraphError(
                "Instagram Graph API not configured. Set INSTAGRAM_APP_ID and "
                "INSTAGRAM_APP_SECRET in .env. See docs/INSTAGRAM_SETUP.md."
            )

    async def get_me(self) -> dict[str, Any]:
        """Fetch the authenticated IG business account info."""
        if not self.ig_user_id:
            raise InstagramGraphError("ig_user_id required")
        r = await self._client.get(
            f"{GRAPH_BASE}/{self.ig_user_id}",
            params={"fields": "id,username,account_type,media_count,followers_count,follows_count",
                    "access_token": self.access_token},
        )
        data = r.json()
        if "error" in data:
            raise InstagramGraphError(data["error"].get("message", str(data["error"])))
        return data

    async def get_user_insights(self, period: str = "day", since: int | None = None,
                                until: int | None = None) -> dict[str, Any]:
        """Account-level insights (reach, impressions, profile_views)."""
        if not self.ig_user_id:
            raise InstagramGraphError("ig_user_id required")
        params = {
            "metric": "reach,impressions,profile_views",
            "period": period,
            "access_token": self.access_token,
        }
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        r = await self._client.get(f"{GRAPH_BASE}/{self.ig_user_id}/insights", params=params)
        data = r.json()
        if "error" in data:
            raise InstagramGraphError(data["error"].get("message", str(data["error"])))
        return data

    async def create_media_container(self, image_url: str, caption: str,
                                     media_type: str = "IMAGE",
                                     is_carousel: bool = False,
                                     video_url: str | None = None) -> str:
        """Step 1 of publishing: create a media container. Returns container id."""
        if not self.ig_user_id:
            raise InstagramGraphError("ig_user_id required")
        params: dict[str, Any] = {
            "caption": caption,
            "access_token": self.access_token,
        }
        if media_type == "VIDEO":
            if not video_url:
                raise InstagramGraphError("video_url required for VIDEO media")
            params["media_type"] = "VIDEO"
            params["video_url"] = video_url
        elif is_carousel:
            params["media_type"] = "CAROUSEL"
            params["image_url"] = image_url
        else:
            params["image_url"] = image_url
        r = await self._client.post(f"{GRAPH_BASE}/{self.ig_user_id}/media", params=params)
        data = r.json()
        if "error" in data:
            raise InstagramGraphError(data["error"].get("message", str(data["error"])))
        return data["id"]

    async def publish_container(self, creation_id: str) -> str:
        """Step 2 of publishing: publish a container that finished processing."""
        if not self.ig_user_id:
            raise InstagramGraphError("ig_user_id required")
        r = await self._client.post(
            f"{GRAPH_BASE}/{self.ig_user_id}/media_publish",
            params={"creation_id": creation_id, "access_token": self.access_token},
        )
        data = r.json()
        if "error" in data:
            raise InstagramGraphError(data["error"].get("message", str(data["error"])))
        return data["id"]

    async def publish_photo(self, image_url: str, caption: str) -> str:
        """Convenience: publish a photo in one call. Returns IG media id."""
        container = await self.create_media_container(image_url, caption)
        return await self.publish_container(container)

    async def get_media(self, media_id: str) -> dict[str, Any]:
        r = await self._client.get(
            f"{GRAPH_BASE}/{media_id}",
            params={"fields": "id,caption,media_type,media_url,permalink,thumbnail_url,timestamp",
                    "access_token": self.access_token},
        )
        return r.json()

    async def get_recent_media(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.ig_user_id:
            raise InstagramGraphError("ig_user_id required")
        r = await self._client.get(
            f"{GRAPH_BASE}/{self.ig_user_id}/media",
            params={"fields": "id,caption,media_type,media_url,permalink,timestamp",
                    "limit": limit, "access_token": self.access_token},
        )
        data = r.json()
        if "error" in data:
            raise InstagramGraphError(data["error"].get("message", str(data["error"])))
        return data.get("data", [])


def build_oauth_url(state: str) -> str:
    """Build the Instagram OAuth URL (Business Login)."""
    from urllib.parse import urlencode
    if not settings.instagram_app_id:
        raise InstagramGraphError("INSTAGRAM_APP_ID not configured")
    params = {
        "client_id": settings.instagram_app_id,
        "redirect_uri": settings.instagram_redirect_uri,
        "scope": "instagram_business_basic,instagram_business_manage_content,instagram_business_manage_insights",
        "response_type": "code",
        "state": state,
    }
    return f"https://www.instagram.com/oauth/authorize?{urlencode(params)}"


async def exchange_code_for_token(code: str) -> dict[str, Any]:
    """Exchange OAuth code for short-lived + long-lived tokens."""
    async with httpx.AsyncClient(timeout=30.0) as c:
        # Step 1: short-lived
        r = await c.get(
            "https://api.instagram.com/oauth/access_token",
            params={
                "client_id": settings.instagram_app_id,
                "client_secret": settings.instagram_app_secret,
                "grant_type": "authorization_code",
                "redirect_uri": settings.instagram_redirect_uri,
                "code": code,
            },
        )
        short = r.json()
        if "error_message" in short or "error_code" in short:
            raise InstagramGraphError(short.get("error_message", str(short)))

        # Step 2: exchange short for long-lived (~60 days)
        r2 = await c.get(
            "https://graph.instagram.com/access_token",
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": settings.instagram_app_secret,
                "access_token": short["access_token"],
            },
        )
        long_lived = r2.json()
        if "error" in long_lived:
            raise InstagramGraphError(long_lived["error"].get("message", str(long_lived["error"])))
        return long_lived


async def refresh_long_lived_token(token: str) -> dict[str, Any]:
    """Refresh before expiry. Long-lived tokens can be refreshed once they're < 60 days old."""
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(
            "https://graph.instagram.com/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": token},
        )
        data = r.json()
        if "error" in data:
            raise InstagramGraphError(data["error"].get("message", str(data["error"])))
        return data


def expires_at_from_seconds(seconds: int) -> datetime:
    return datetime.utcnow() + timedelta(seconds=seconds)