import os
from datetime import datetime, timezone
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

CLIENT_ID = os.environ.get("GMAIL_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GMAIL_CLIENT_SECRET")
REDIRECT_URI = os.environ.get("GMAIL_REDIRECT_URI")


def _get_setting(db: Session, key: str) -> str | None:
    from models import Settings
    row = db.query(Settings).filter(Settings.key == key).first()
    return row.value if row else None


def _set_setting(db: Session, key: str, value: str):
    from models import Settings
    row = db.query(Settings).filter(Settings.key == key).first()
    if row:
        row.value = value
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(Settings(key=key, value=value))
    db.commit()


def get_credentials(db: Session) -> Credentials | None:
    refresh_token = _get_setting(db, "gmail_refresh_token")
    if not refresh_token:
        return None

    creds = Credentials(
        token=_get_setting(db, "gmail_access_token"),
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=SCOPES,
    )

    # Refresh if expired or no access token
    if not creds.token or creds.expired:
        creds.refresh(Request())
        _set_setting(db, "gmail_access_token", creds.token)

    return creds


def get_gmail_service(db: Session):
    creds = get_credentials(db)
    if not creds:
        raise ValueError("Gmail not connected")
    return build("gmail", "v1", credentials=creds)


def is_connected(db: Session) -> bool:
    return _get_setting(db, "gmail_refresh_token") is not None


def save_tokens(db: Session, refresh_token: str, access_token: str, connected_email: str):
    _set_setting(db, "gmail_refresh_token", refresh_token)
    _set_setting(db, "gmail_access_token", access_token)
    _set_setting(db, "gmail_connected_email", connected_email)


def get_connected_email(db: Session) -> str | None:
    return _get_setting(db, "gmail_connected_email")


def get_last_synced(db: Session) -> str | None:
    return _get_setting(db, "gmail_last_synced")


def set_last_synced(db: Session):
    _set_setting(db, "gmail_last_synced", datetime.now(timezone.utc).isoformat())
