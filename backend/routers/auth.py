import os
from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from google_auth_oauthlib.flow import Flow
import google.oauth2.id_token
import google.auth.transport.requests

from database import get_db
import gmail_client

router = APIRouter(prefix="/api/auth", tags=["auth"])

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")


def _make_flow():
    return Flow.from_client_config(
        {
            "web": {
                "client_id": gmail_client.CLIENT_ID,
                "client_secret": gmail_client.CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [gmail_client.REDIRECT_URI],
            }
        },
        scopes=SCOPES,
        redirect_uri=gmail_client.REDIRECT_URI,
    )


@router.get("/gmail")
def gmail_auth_start():
    """Redirect browser to Google OAuth consent screen."""
    flow = _make_flow()
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",  # force refresh token to be returned every time
    )
    return RedirectResponse(auth_url)


@router.get("/gmail/callback")
def gmail_auth_callback(code: str, db: Session = Depends(get_db)):
    """Handle OAuth callback, store tokens, redirect to frontend."""
    flow = _make_flow()
    flow.fetch_token(code=code)

    creds = flow.credentials
    refresh_token = creds.refresh_token
    access_token = creds.token

    # Get the connected email address
    import googleapiclient.discovery
    service = googleapiclient.discovery.build("gmail", "v1", credentials=creds)
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
