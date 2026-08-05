# Social Ultimate

Unified Instagram automation + social media management, built by merging:
- **[ohld/igbot](https://github.com/ohld/igbot)** — bot patterns (wrapped, gated)
- **[eaabak/instagram-auto-create-account](https://github.com/eaabak/instagram-auto-create-account)** — account creation patterns (reference only)
- **[mithulix/Social-Media-Dashboard](https://github.com/mithulix/Social-Media-Dashboard)** — dashboard UI patterns
- **[Katzca/AutoSocial](https://github.com/Katzca/AutoSocial)** — scheduler patterns
- **[InstaPy/InstaPy](https://github.com/InstaPy/InstaPy)** — quota/feature reference (patterns only; Selenium API surface obsolete)
- **[tducasse/go-instabot](https://github.com/tducasse/go-instabot)** — archived, not used

---

## What's actually usable

This repo has **two layers**, by design:

### ✅ Production layer (works today, legal)
Uses **Meta's official Instagram Graph API** (v18+). Requires:
- A Facebook App with the **Instagram** product enabled
- A **Business or Creator** Instagram account
- User-granted OAuth permission

Features:
- Multi-account OAuth connection
- Post publishing (image/video)
- Post scheduling (APScheduler, server-side)
- Account analytics (followers, reach, impressions, profile views)
- Recent media listing
- Dashboard UI (vanilla JS, single binary, no Node build)

### ⚠ Experimental layer (gated, opt-in)
Wraps the Selenium automation patterns from `igbot` and `eaabak`. **Almost every action here violates Instagram ToS.** Accounts that use these get banned in hours.

Gating:
- Disabled by default (`EXPERIMENTAL_ENABLED=false`)
- When enabled, endpoints still require `consent_acknowledged=true` per request
- The account-creation module is **intentionally not implemented** — only the reference structure from `eaabak` lives in `app/experimental/account_creator.py`. See `docs/EXPERIMENTAL.md`.

---

## Quick start

### Local — Docker (recommended)

```bash
cp .env.example .env       # fill in DATABASE_URL, Instagram creds if you have them
cd docker
docker compose up --build
```

Open http://localhost:8000 → register an account → connect Instagram.

### Local — bare Python (SQLite, no Instagram API)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=sqlite:///./social_ultimate.db
uvicorn app.main:app --reload
```

Open http://localhost:8000.

### Deploy — Render

See `docs/DEPLOY.md`. One click: pushes to `main` auto-deploy.

---

## Architecture

```
app/
├── main.py              FastAPI entry, mounts static + routers
├── core/
│   ├── config.py        Settings (env-driven)
│   ├── security.py      bcrypt + JWT
│   ├── instagram.py     Instagram Graph API client (production)
│   └── experimental_gate.py   Gating for experimental routes
├── db/
│   ├── models.py        SQLAlchemy models
│   └── session.py       engine + init_db
├── api/
│   ├── auth.py          /api/auth/{register,login,me}
│   ├── instagram.py     /api/instagram/{accounts,publish,oauth}
│   ├── posts.py         /api/posts  (schedule)
│   ├── experimental.py  /api/experimental/*  (gated)
│   └── health.py        /health
├── bot/
│   └── instabot.py      Selenium bot core (experimental, driver-injected)
├── experimental/
│   └── account_creator.py   Selenium account creator stub (experimental)
└── scheduler/
    └── jobs.py          APScheduler integration

web/public/              Single-page dashboard (HTML/CSS/vanilla JS)
docker/                  Dockerfile + compose
docs/                    INSTAGRAM_SETUP, EXPERIMENTAL, DEPLOY
```

---

## Endpoints (production)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness, feature flags |
| POST | `/api/auth/register` | Create account |
| POST | `/api/auth/login` | Get JWT |
| GET | `/api/auth/me` | Who am I |
| GET | `/api/instagram/oauth/start` | Begin Instagram OAuth |
| GET | `/api/instagram/oauth/callback` | Complete OAuth |
| GET | `/api/instagram/accounts` | List connected accounts |
| GET | `/api/instagram/accounts/{id}/me` | Account profile |
| GET | `/api/instagram/accounts/{id}/insights` | Reach / impressions / views |
| GET | `/api/instagram/accounts/{id}/media` | Recent posts |
| POST | `/api/instagram/publish` | Publish now |
| POST | `/api/posts` | Schedule a post |
| GET | `/api/posts` | List scheduled posts |
| DELETE | `/api/posts/{id}` | Cancel scheduled post |

## Endpoints (experimental, gated)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/experimental/bot/jobs` | Queue automation job |
| GET | `/api/experimental/bot/jobs` | List jobs |
| POST | `/api/experimental/accounts/create` | Stub — returns 501 |

---

## Tests

```bash
pytest
```

See `tests/test_smoke.py` for the minimal end-to-end check.

---

## License

MIT. See upstream repos' licenses for attribution:
- ohld/igbot — MIT
- InstaPy/InstaPy — GPLv2
- Katzca/AutoSocial — MIT
- tducasse/go-instabot — MIT
- eaabak/instagram-auto-create-account — see LICENSE.md
- mithulix/Social-Media-Dashboard — MIT