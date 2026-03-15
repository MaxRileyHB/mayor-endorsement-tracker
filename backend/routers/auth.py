import os
from urllib.parse import urlencode

import requests as http_requests
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from database import get_db
import gmail_client

router = APIRouter(prefix="/api/auth", tags=["auth"])

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")


@router.get("/gmail")
def gmail_auth_start():
    """Redirect browser to Google OAuth consent screen."""
    params = {
        "client_id": gmail_client.CLIENT_ID,
        "redirect_uri": gmail_client.REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = "https://accounts.google.com/o/oauth2/auth?" + urlencode(params)
    return RedirectResponse(auth_url)


@router.get("/gmail/callback")
def gmail_auth_callback(code: str, db: Session = Depends(get_db)):
    """Exchange auth code for tokens and store them."""
    # Direct token exchange — no PKCE library magic
    resp = http_requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": gmail_client.CLIENT_ID,
            "client_secret": gmail_client.CLIENT_SECRET,
            "code": code,
            "redirect_uri": gmail_client.REDIRECT_URI,
            "grant_type": "authorization_code",
        },
    )

    if not resp.ok:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {resp.text}")

    tokens = resp.json()
    refresh_token = tokens.get("refresh_token")
    access_token = tokens.get("access_token")

    if not refresh_token:
        raise HTTPException(
            status_code=400,
            detail="No refresh token returned. Revoke app access in your Google account and try again.",
        )

    # Get connected email address
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=gmail_client.CLIENT_ID,
        client_secret=gmail_client.CLIENT_SECRET,
        scopes=SCOPES,
    )
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    email = profile.get("emailAddress", "")

    gmail_client.save_tokens(db, refresh_token, access_token, email)

    return RedirectResponse(f"{FRONTEND_URL}?gmail=connected")


@router.get("/status")
def auth_status(db: Session = Depends(get_db)):
    return {
        "connected": gmail_client.is_connected(db),
        "email": gmail_client.get_connected_email(db),
        "last_synced": gmail_client.get_last_synced(db),
    }


@router.post("/gmail/disconnect")
def gmail_disconnect(db: Session = Depends(get_db)):
    from models import Settings
    db.query(Settings).filter(Settings.key.in_([
        "gmail_refresh_token", "gmail_access_token",
        "gmail_connected_email", "gmail_last_synced",
    ])).delete(synchronize_session=False)
    db.commit()
    return {"disconnected": True}
