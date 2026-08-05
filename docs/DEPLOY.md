# Deploying to Render

## One-time setup

1. Push this repo to GitHub
2. In Render dashboard → "New +" → "Blueprint"
3. Connect the repo; Render will read `render.yaml`
4. Set environment variables in the Render dashboard:
   - `SECRET_KEY` (use `python -c "import secrets; print(secrets.token_urlsafe(48))"`)
   - `INSTAGRAM_APP_ID` / `INSTAGRAM_APP_SECRET`
   - `INSTAGRAM_REDIRECT_URI` (your Render URL + `/api/instagram/oauth/callback`)

## Database

This repo includes `render.yaml` that provisions a free Postgres instance.
For production scale, upgrade to a paid tier — Render's free Postgres
expires after 90 days.

## Auto-deploy

Pushes to `main` trigger a redeploy. Verify health:

```bash
curl https://<your-app>.onrender.com/health
```

## Local testing against prod database

```bash
export DATABASE_URL=<render_internal_db_url>
uvicorn app.main:app --reload
```

## Logs

Render dashboard → your service → "Logs". The scheduler logs each
post-publish attempt and its outcome.