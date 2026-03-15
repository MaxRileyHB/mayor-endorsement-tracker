# Gmail Integration Plan
## Mayor Endorsement CRM — Ben Allen for Insurance Commissioner

**Author:** Max Riley
**Date:** March 2026
**Status:** Pre-implementation — ready to build

---

## Overview

This document is the complete plan for integrating Gmail into the Mayor Endorsement CRM. It covers the technical architecture, step-by-step build order, manual setup instructions Max needs to complete, known risks, and a full feature roadmap including everything beyond V1.

**Context:**
- Single user (Max Riley), Google Workspace account on `@benallenca.com`
- Campaign Gmail account used exclusively for mayor outreach
- OAuth tokens stored in the PostgreSQL database (not env vars) for robustness
- App deployed on Railway — the Railway URL is the production redirect URI
- From name on all outreach: `Max Riley - Ben Allen for Insurance Commissioner`
- V1 scope: Auth + Send approved drafts + Sync inbox. Reply-from-app is Phase 3.

---

## How Gmail Connects to the Existing System

There are four places Gmail touches what's already built:

### 1. Review Queue → Send Button
The "Send N approved" button at the bottom of the Review Queue currently shows a placeholder alert. This is the primary send path. After integration, it calls `POST /api/drafts/send`, which sends each approved draft via the Gmail API, marks it sent, and logs everything.

### 2. City Detail Panel → Timeline
The Timeline section (emails + calls) currently only shows manually logged calls. Email sync populates it with real sent and received messages. Every outreach email you send and every reply a mayor sends back appears here automatically.

### 3. Status Auto-Advance on Send
When a draft is sent, the city's pipeline status should automatically advance:
- `info_request` sent → city status → `info_requested`
- `endorsement_outreach` sent → city status → `outreach_sent`
This also updates `last_contacted` and writes an `activity_log` entry.

### 4. Compose / Reply (Phase 3)
The spec calls for a Compose button in the city detail panel for writing individual replies. Not in V1, but the timeline UI is already scaffolded for it.

---

## Architecture

### Token Storage: `settings` table
A simple key-value table in PostgreSQL stores the OAuth tokens:

```sql
CREATE TABLE settings (
  key VARCHAR(100) PRIMARY KEY,
  value TEXT,
  updated_at TIMESTAMP DEFAULT NOW()
);
```

Rows used:
- `gmail_refresh_token` — long-lived, used to get new access tokens
- `gmail_access_token` — short-lived (1 hour), cached to avoid unnecessary refreshes
- `gmail_token_expiry` — ISO timestamp of when access token expires
- `gmail_connected_email` — the email address that's connected (for display)

**Why DB instead of env vars:** Railway env var changes require a redeploy. More importantly, Google occasionally rotates refresh tokens on security events (password change, revocation, token inactivity > 6 months). Storing in DB means the rotated token is automatically saved on next refresh without any manual intervention.

### Backend Packages
```
google-auth
google-auth-oauthlib
google-api-python-client
```

These are the official Google client libraries. `google-auth` handles token refresh automatically.

### New Backend Files
- `routers/auth.py` — OAuth flow endpoints (`/api/auth/gmail`, `/api/auth/gmail/callback`, `/api/auth/status`)
- `routers/emails.py` — Send and sync endpoints (`/api/drafts/send`, `/api/emails/sync`)
- `gmail_client.py` — Shared helper: builds authenticated Gmail API service, handles token refresh

### New Frontend Pieces
- Gmail connection status indicator in the app header
- Wired-up Send button in Review Queue
- Manual sync button + "last synced" timestamp in the header or settings area

---

## Part 1: Manual Setup — Google Cloud Console

**Max must complete these steps in the browser before any code runs.**

### Step 1: Create a Google Cloud Project
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Sign in with your `@benallenca.com` Google Workspace account
3. Click the project dropdown (top left, next to "Google Cloud") → **New Project**
4. Name it `Mayor Endorsement CRM` → **Create**
5. Wait ~30 seconds for it to provision, then make sure it's selected in the dropdown

### Step 2: Enable the Gmail API
1. In the left sidebar: **APIs & Services → Library**
2. Search for `Gmail API`
3. Click it → **Enable**

### Step 3: Configure the OAuth Consent Screen
1. **APIs & Services → OAuth consent screen**
2. **User Type: Internal** ← critical. Since `@benallenca.com` is a Google Workspace org, "Internal" means only users in your org can authorize. This skips Google's public app verification entirely — no scary warning screen.
3. Click **Create**
4. Fill in:
   - App name: `Mayor CRM`
   - User support email: your `@benallenca.com` address
   - Developer contact email: same
5. Click **Save and Continue**
6. On the Scopes screen: click **Add or Remove Scopes**
   - Search for and add: `https://www.googleapis.com/auth/gmail.send`
   - Search for and add: `https://www.googleapis.com/auth/gmail.readonly`
   - (These give read access for sync and send access for outreach)
7. **Save and Continue** through the rest → **Back to Dashboard**

### Step 4: Create OAuth Credentials
1. **APIs & Services → Credentials**
2. **+ Create Credentials → OAuth client ID**
3. Application type: **Web application**
4. Name: `Mayor CRM Web Client`
5. Under **Authorized redirect URIs**, add both:
   - `http://localhost:8000/api/auth/gmail/callback` (for local dev)
   - `https://[your-railway-backend-url]/api/auth/gmail/callback` (for production)
   - You need the actual Railway URL here — find it in your Railway dashboard under the backend service
6. Click **Create**
7. A dialog shows your **Client ID** and **Client Secret** — copy both immediately
8. Add them to Railway environment variables:
   - `GMAIL_CLIENT_ID` = the client ID
   - `GMAIL_CLIENT_SECRET` = the client secret
   - Also add these to your local `.env` file for dev

### Step 5: First-Time Authorization
Once the backend is deployed with the auth routes:
1. Visit `https://[railway-backend-url]/api/auth/gmail` in your browser
2. You'll be redirected to Google's sign-in page
3. Sign in with the campaign Gmail account (the one you'll use for outreach)
4. Approve the permissions
5. You'll be redirected back to the app with a success message
6. The refresh token is now stored in the database — you won't need to do this again

---

## Part 2: Build Plan (Phased)

### Phase 1 — Auth + Send ✦ Core unlock

**Backend:**

1. **`settings` table migration** — add the key-value table to the DB
2. **`gmail_client.py`** — helper module that:
   - Reads credentials from env vars
   - Loads refresh token from `settings` table
   - Builds an authenticated `googleapiclient` service object
   - Saves any rotated tokens back to DB
3. **`routers/auth.py`** with:
   - `GET /api/auth/gmail` — builds Google OAuth URL with correct scopes and redirect URI, redirects the browser to it
   - `GET /api/auth/gmail/callback` — receives the `code` param from Google, exchanges for tokens, saves refresh token to DB, redirects to frontend with success flag
   - `GET /api/auth/status` — returns `{ connected: bool, email: str | null, last_synced: str | null }` — the frontend polls this to show connection status
4. **`POST /api/drafts/send`** in `routers/emails.py`:
   - Accepts `{ draft_ids: [int] }` or `{ batch_id: str }`
   - For each approved draft:
     - Fetches draft + city from DB
     - Determines recipient: `mayor_email` if set, else `city_email`
     - Builds RFC 2822 message with correct From/To/Subject/Body headers
     - Sets From: `Max Riley - Ben Allen for Insurance Commissioner <campaign@benallenca.com>`
     - Sends via `gmail.users.messages.send`
     - Marks draft `status = 'sent'`, sets `sent_at`
     - Creates a row in `emails` table (direction='outbound')
     - Updates city `last_contacted = now()`
     - Auto-advances city status (info_request → info_requested, endorsement_outreach → outreach_sent)
     - Logs to `activity_log`
   - Returns `{ sent: N, failed: [...] }`

**Frontend:**

5. **Auth status in header** — small indicator showing "Gmail connected ✓" or "Connect Gmail" link. Clicking it goes to `/api/auth/gmail` to start the OAuth flow.
6. **Review Queue send button** — wire to `POST /api/drafts/send`, show sending state, refresh draft list on success

### Phase 2 — Sync (inbox → timeline)

**Backend:**

7. **`POST /api/emails/sync`** in `routers/emails.py`:
   - Calls `gmail.users.messages.list` with `maxResults=100`, filtering to the last sync date
   - For each message, calls `gmail.users.messages.get` to fetch full headers + body
   - Extracts: Message-ID, Thread-ID, From, To, Subject, Date, body text (prefers plain, falls back to HTML-stripped)
   - Runs city matching (see below)
   - Upserts into `emails` table using `gmail_message_id` as unique key
   - Updates `settings.gmail_last_synced`
   - Returns `{ synced: N, matched: N, unmatched: N }`

**City matching logic (in priority order):**
```
1. Check if gmail_thread_id matches any thread_id in emails table → guaranteed match, same city
2. Exact match: sender or recipient address == city.mayor_email or city.city_email (case-insensitive)
3. Domain match: extract domain from sender → check against city.city_website (strip www, normalize)
4. No match → log as unmatched, skip (or store with city_id=NULL for the unmatched inbox view)
```

8. **Update `GET /api/cities/{id}/emails`** — already exists, no change needed. The synced emails automatically appear in the timeline.

**Frontend:**

9. **Auto-sync on app load** — call `POST /api/emails/sync` once when the app mounts (if Gmail is connected)
10. **Manual sync button** — in the header, "Sync Gmail" button with a spinning indicator and "last synced X min ago" label
11. **City panel timeline auto-refresh** — after a sync, if the current city panel is open, refresh its emails

### Phase 3 — Reply from City Panel

**Backend:**

12. **`POST /api/emails/reply`**:
   - Accepts `{ city_id, body, subject, in_reply_to_message_id }`
   - Builds reply with correct `In-Reply-To` and `References` headers for threading
   - Sends via Gmail API
   - Logs to `emails` table
   - Updates city `last_contacted`

**Frontend:**

13. **Reply button on email rows** in the Timeline — clicking opens an inline compose box below that email
14. **Standalone compose** — "Compose email" button in the city panel header for fresh (non-reply) messages

---

## Part 3: Feature Roadmap (Beyond V1)

These are real features worth building after Phase 1-2 are solid.

### High-value additions

**Unmatched emails inbox**
A separate view (accessible from the header) showing emails that synced from Gmail but couldn't be matched to a city. Shows From, Subject, Date, and a "Assign to city" button that lets you link it manually. These then appear in that city's timeline.

**Read/unread tracking**
Store whether each email has been viewed. Show a blue dot or bold city name in the kanban when a city has an unread reply. The Gmail API returns `labelIds` — the `UNREAD` label tells you this without extra API calls.

**Sync on city panel open**
When you open a city's detail panel, trigger a targeted sync for that city's known email addresses. This gives you the freshest data without syncing the entire inbox.

**Gmail label management**
Automatically apply a Gmail label (e.g., "Mayor Outreach / Sent") to every email sent through the app. Makes it easy to find them in Gmail directly. Use `gmail.users.messages.modify` after send.

**Email search across all cities**
A global search within the emails table — useful when you remember "I had a conversation with someone in LA county about FAIR Plan" but don't remember which city.

**Auto-advance on reply received**
When a mayor replies (inbound email synced and matched), auto-advance the city status from `outreach_sent` or `info_requested` → `in_conversation`. Could be a setting Max can toggle.

**Delivery failure detection**
Gmail sends bounce/failure notifications back to the inbox. Detect "mailer-daemon" or "delivery failed" subjects in the sync and flag the city's email address as invalid.

**Periodic background sync**
A browser `setInterval` (every 5 minutes while the app is open) calling `/api/emails/sync` in the background. The spec calls for this. Simple to add once sync is working.

**Gmail Pub/Sub push notifications (advanced)**
Instead of polling, Google can push a notification to a webhook whenever new mail arrives. This requires setting up a Google Cloud Pub/Sub topic and a public HTTPS webhook on Railway. Real-time but significantly more complex to set up. Not worth it until polling is solid.

---

## Part 4: Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Refresh token rotated by Google | Low | High | Store token in DB, auto-save rotated tokens; build re-auth UI |
| OAuth redirect URI mismatch (dev vs prod) | Medium | Medium | Register both localhost and Railway URI in Google Cloud Console |
| Email body encoding issues (base64url, HTML) | High | Low | Strip HTML tags, decode base64url properly; plain text preferred |
| City matching fails on unusual email domains | High | Medium | Build unmatched inbox view; allow manual assignment |
| Gmail API rate limit hit during bulk send | Low | High | Add 100ms delay between sends; handle 429 with retry |
| Mayor replies from a different address than what we have on record | Medium | Medium | Thread-ID matching catches this if we initiated the thread |
| Google Workspace "Internal" app type unavailable | Low | Medium | Workspace Basic and above supports Internal — confirm org tier |
| Railway deployment URL changes | Low | High | Railway custom domains are stable; avoid using auto-generated URLs for OAuth |

---

## Part 5: API Endpoint Summary

```
# Auth
GET  /api/auth/gmail                    Start OAuth flow (redirects to Google)
GET  /api/auth/gmail/callback           OAuth callback — exchanges code for tokens
GET  /api/auth/status                   { connected, email, last_synced }
POST /api/auth/gmail/disconnect         Clears stored tokens

# Send
POST /api/drafts/send                   Send approved drafts via Gmail
  Body: { draft_ids: [int] }
  Returns: { sent: N, failed: [{ draft_id, error }] }

# Sync
POST /api/emails/sync                   Pull new Gmail messages, match to cities
  Returns: { synced: N, matched: N, unmatched: N }

GET  /api/emails/unmatched              Emails that couldn't be matched to a city
POST /api/emails/assign                 Manually assign an email to a city
  Body: { email_id: int, city_id: int }

# Reply (Phase 3)
POST /api/emails/reply                  Send a reply to a specific email thread
  Body: { city_id, body, subject, in_reply_to_message_id }
```

---

## Part 6: Data Model Additions

### `settings` table (new)
```sql
CREATE TABLE settings (
  key VARCHAR(100) PRIMARY KEY,
  value TEXT,
  updated_at TIMESTAMP DEFAULT NOW()
);
```

Keys used: `gmail_refresh_token`, `gmail_access_token`, `gmail_token_expiry`, `gmail_connected_email`, `gmail_last_synced`

### `emails` table (existing — minor additions)
The existing `emails` table is already correctly designed for this. The only addition:
- `gmail_thread_id` — already in schema, will be populated during sync

---

## Part 7: Environment Variables

Add to both Railway and local `.env`:

```
GMAIL_CLIENT_ID=...
GMAIL_CLIENT_SECRET=...
GMAIL_REDIRECT_URI_LOCAL=http://localhost:8000/api/auth/gmail/callback
GMAIL_REDIRECT_URI_PROD=https://[railway-backend-url]/api/auth/gmail/callback
```

The app detects which redirect URI to use based on whether it's running in Railway (check for `RAILWAY_ENVIRONMENT` env var) or locally.

---

## Current Status

- [x] `emails` table exists in DB schema
- [x] `GET /api/cities/{id}/emails` endpoint exists
- [x] Timeline UI in city detail panel (shows emails + calls)
- [x] Review Queue send button (placeholder)
- [ ] Google Cloud project + OAuth credentials (Max to set up)
- [ ] `settings` table
- [ ] `gmail_client.py`
- [ ] Auth routes
- [ ] `POST /api/drafts/send`
- [ ] `POST /api/emails/sync`
- [ ] Frontend auth status indicator
- [ ] Frontend sync trigger
