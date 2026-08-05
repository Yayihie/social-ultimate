# Setting up Instagram Graph API access

The production layer requires:

1. A Facebook App
2. An Instagram Business or Creator account
3. A Facebook Page connected to that Instagram account
4. App review for the scopes you need

## Steps

### 1. Create a Facebook App
- Go to https://developers.facebook.com/apps
- "Create App" → type "Other" → "Business"
- Note the **App ID** and **App Secret** (Settings → Basic)

### 2. Add the Instagram product
- In your App dashboard → "Add Product" → **Instagram** → "Set Up"
- Use the **Instagram Graph API** (not Basic Display — that one is being deprecated)

### 3. Convert your Instagram account to Business/Creator
- Instagram app → Settings → Account → "Switch to Professional Account"
- This requires a connected Facebook Page

### 4. Configure OAuth redirect
- In your App Settings → "Instagram Graph API" → "OAuth redirect URIs"
- Add: `http://localhost:8000/api/instagram/oauth/callback` (and your prod URL)

### 5. App Review (for live use)
- The basic scopes (`instagram_business_basic`, `instagram_business_manage_content`,
  `instagram_business_manage_insights`) work in development mode for accounts you own.
- For real users, you must submit your app for review. Approval takes days to weeks.

## Fill in .env

```bash
INSTAGRAM_APP_ID=<your_app_id>
INSTAGRAM_APP_SECRET=<your_app_secret>
INSTAGRAM_REDIRECT_URI=http://localhost:8000/api/instagram/oauth/callback
```

Restart the app. Click "Connect Instagram" in the dashboard.

## Scopes used by this app

| Scope | Used for |
|-------|----------|
| `instagram_business_basic` | Read basic profile info |
| `instagram_business_manage_content` | Publish media |
| `instagram_business_manage_insights` | Read analytics |

## Rate limits

- 200 API calls per hour per user
- 25 posts per day per user
- 50 publishes per 24h per account

The scheduler respects `scheduled_for`; if you queue a flood of posts, the API
will start returning errors and the affected posts will be marked `failed`.