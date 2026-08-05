"""Unit tests for the experimental bot — verify config validation
without needing a real browser.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.bot.instabot import BotConfig, BotStats, InstagramBot
from app.experimental.account_creator import (
    generate_username, generate_password, generate_user_info, AccountCreator
)


def test_bot_config_defaults_are_conservative():
    cfg = BotConfig(username="x", password="y")
    assert cfg.like_per_day <= 200
    assert cfg.action_min_delay >= 10


def test_bot_run_emits_progress_and_honors_stop():
    events = []
    bot = InstagramBot(driver=None, config=BotConfig(username="u", password="p",
                                                      target_tags=["fitness"]))
    bot.on_progress(lambda e, p: events.append(e))
    bot._stop = True  # stop immediately
    stats = bot.run()
    assert stats.errors >= 1 or "bot_stop" in events


def test_account_creator_refuses_to_run():
    creator = AccountCreator(driver=None)
    result = creator.create_one()
    assert result.success is False
    assert "intentionally" in (result.error or "").lower()


def test_generators_produce_unique_values():
    names = {generate_username() for _ in range(50)}
    assert len(names) >= 45  # allow rare collisions
    pw = generate_password()
    assert len(pw) >= 10


def test_user_info_has_required_fields():
    info = generate_user_info()
    for k in ("first_name", "last_name", "username", "password", "email"):
        assert k in info