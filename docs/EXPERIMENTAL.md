# Experimental module — read this before turning it on

This module wraps Selenium-based Instagram automation from the upstream
repos (ohld/igbot, eaabak/instagram-auto-create-account).

## ⚠ Why this is gated

- **Almost every action violates Instagram's Terms of Service.**
- Instagram actively detects Selenium-driven browsers via:
  - TLS fingerprinting (JA3/JA4)
  - Behavioral heuristics (move timing, scroll patterns)
  - Browser property leaks (`navigator.webdriver`, missing plugins, etc.)
- Accounts that use these patterns get banned in hours to days.
- Meta can also suspend your Facebook App, blocking the entire
  production layer for *all* your users.

## What is actually here

### `app/bot/instabot.py`
A Selenium-driven bot with the same configuration shape as igbot:
follow/unfollow, like-by-tag, comment. Driver is injected so the
module is testable without a browser. The Selenium flows for the
actual `login()`, `like_by_tag()`, etc. methods are **deliberately
left as `NotImplementedError`** — you must implement them yourself,
following the reference patterns in `ohld/igbot/instabot/bot_bot.py`.

The reason: shipping a working bot would invite mass misuse. Shipping
the shape + config + driver integration lets you experiment safely,
in your own account, with full awareness of what you're doing.

### `app/experimental/account_creator.py`
Wraps `eaabak/instagram-auto-create-account` patterns. Like the bot,
the actual signup driver is intentionally stubbed. The file exposes:
- `generate_username()`, `generate_password()`, `generate_user_info()`
  (use these for testing data shapes)
- `AccountCreator` class with a `.create_one()` method that **returns
  a failure** rather than doing anything destructive

If you want to wire up a real creator, the Selenium flow you need is
in `eaabak/instagram-auto-create-account/botAccountCreate.py`. Read
that file, understand every line, then decide if you really want to.

## How to enable (if you really must)

```bash
# .env
EXPERIMENTAL_ENABLED=true
EXPERIMENTAL_REQUIRE_EXPLICIT_OPT_IN=true
```

Then every request to `/api/experimental/*` must include
`consent_acknowledged: true`. This is not a legal shield — it's a
paper trail to confirm the user understood.

## Better alternatives

If your goal is follower growth or engagement:
- Run **Instagram ads** through the official API (`/api/instagram/publish`
  already supports this; just point it at paid content).
- Use **Creator Studio** for scheduling (also free, native to Meta).
- Use **Buffer / Later / Hootsuite** — they're paid but ToS-compliant.

If your goal is research:
- Use a **sandbox account** you've explicitly designated for testing.
- Don't point automation at real users.
- Read https://help.instagram.com/4787455989168 before you do anything.