"""Experimental automation bot.

Sourced from ohld/igbot patterns but stripped of the dead private-API calls
that Instagram has invalidated. This is an interactive Selenium-based bot
that drives a real browser session. Use sparingly.

WARNING: Almost every action here violates Instagram Terms of Service.
Instagram actively detects and bans accounts that use automation.
This module exists for research / educational use only.
"""
from __future__ import annotations
import time
import random
from dataclasses import dataclass, field
from typing import Callable

# The original igbot uses private Instagram HTTP endpoints. We don't.
# Selenium + a real browser is the only thing that vaguely still works
# against live Instagram, and even that is fragile.


@dataclass
class BotConfig:
    """User-tunable knobs. Defaults are conservative."""
    username: str
    password: str
    like_per_day: int = 100
    follow_per_day: int = 80
    unfollow_per_day: int = 100
    comments_per_day: int = 30
    action_min_delay: int = 30       # seconds
    action_max_delay: int = 120      # seconds
    do_like: bool = True
    do_follow: bool = True
    do_unfollow: bool = True
    do_comment: bool = False
    comment_list: list[str] = field(default_factory=list)
    target_tags: list[str] = field(default_factory=list)
    target_users: list[str] = field(default_factory=list)
    unfollow_users: list[str] = field(default_factory=list)
    headless: bool = True
    proxy: str | None = None


@dataclass
class BotStats:
    likes: int = 0
    follows: int = 0
    unfollows: int = 0
    comments: int = 0
    errors: int = 0
    started_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "likes": self.likes,
            "follows": self.follows,
            "unfollows": self.unfollows,
            "comments": self.comments,
            "errors": self.errors,
            "elapsed_seconds": time.time() - self.started_at if self.started_at else 0,
        }


class InstagramBot:
    """Selenium-driven experimental bot.

    The actual driver is injected so tests can use a mock. Real usage:
        driver = webdriver.Chrome(...)
        bot = InstagramBot(driver, BotConfig(...))
        bot.run()
    """

    def __init__(self, driver, config: BotConfig):
        self.driver = driver
        self.config = config
        self.stats = BotStats()
        self._stop = False
        self._progress_cb: Callable[[str, dict], None] | None = None

    def on_progress(self, cb: Callable[[str, dict], None]) -> None:
        self._progress_cb = cb

    def stop(self) -> None:
        self._stop = True

    def _emit(self, event: str, **payload) -> None:
        if self._progress_cb:
            try:
                self._progress_cb(event, {"stats": self.stats.to_dict(), **payload})
            except Exception:
                pass

    def _human_delay(self) -> None:
        delay = random.randint(self.config.action_min_delay, self.config.action_max_delay)
        self._emit("delay", seconds=delay)
        time.sleep(delay)

    def login(self) -> bool:
        """Login flow. Implementation depends on having a real driver."""
        raise NotImplementedError(
            "Selenium login flow must be implemented against your target "
            "Instagram version. See docs/EXPERIMENTAL.md for the reference "
            "implementation pattern from igbot."
        )

    def like_by_tag(self, tag: str, amount: int) -> int:
        self._emit("like_by_tag_start", tag=tag, amount=amount)
        return 0  # placeholder; real impl drives the browser

    def follow_user(self, username: str) -> bool:
        self._emit("follow", username=username)
        return False

    def unfollow_user(self, username: str) -> bool:
        self._emit("unfollow", username=username)
        return False

    def comment_on_post(self, url: str, text: str) -> bool:
        self._emit("comment", url=url, text=text)
        return False

    def run(self) -> BotStats:
        """Run the configured automation. Honors self._stop for graceful abort."""
        self.stats.started_at = time.time()
        self._emit("bot_start", config=self.config.username)
        try:
            if not self.login():
                self._emit("bot_login_failed")
                self.stats.errors += 1
                return self.stats
            # Iterate configured actions in a loop, with human-like delays
            for tag in self.config.target_tags:
                if self._stop:
                    break
                if self.config.do_like:
                    self.like_by_tag(tag, self.config.like_per_day // max(len(self.config.target_tags), 1))
                    self._human_delay()
            self._emit("bot_stop", stats=self.stats.to_dict())
        except Exception as e:
            self._emit("bot_error", error=str(e))
            self.stats.errors += 1
        return self.stats