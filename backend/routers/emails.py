import base64
import re
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Draft, City, Email, ActivityLog
import gmail_client

router = APIRouter(prefix="/api", tags=["emails"])

FROM_NAME = "Max Riley - Ben Allen for Insurance Commissioner"

STATUS_ADVANCE = {
    "info_request": "info_requested",
    "endorsement_outreach": "outreach_sent",
}


class SendRequest(BaseModel):
    draft_ids: Optional[List[int]] = None
    batch_id: Optional[str] = None


def _build_message(to: str, subject: str, body: str, from_email: str) -> dict:
    # Normalize line endings so the email renders cleanly
    body = body.replace('\r\n', '\n').replace('\r', '\n')
    message = MIMEMultipart("alternative")
    message["To"] = to
    message["From"] = f"{FROM_NAME} <{from_email}>"
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain", "utf-8"))
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {"raw": raw}


@router.post("/drafts/send")
def send_drafts(payload: SendRequest, db: Session = Depends(get_db)):
    if not gmail_client.is_connected(db):
        raise HTTPException(status_code=400, detail="Gmail not connected")

    # Resolve which drafts to send
    if payload.draft_ids:
        drafts = db.query(Draft).filter(
            Draft.id.in_(payload.draft_ids),
            Draft.status.in_(["approved", "edited"]),
        ).all()
    elif payload.batch_id:
        drafts = db.query(Draft).filter(
            Draft.batch_id == payload.batch_id,
            Draft.status.in_(["approved", "edited"]),
        ).all()
    else:
        raise HTTPException(status_code=400, detail="Provide draft_ids or batch_id")

    if not drafts:
        raise HTTPException(status_code=400, detail="No approved drafts found")

    try:
        service = gmail_client.get_gmail_service(db)
        profile = service.users().getProfile(userId="me").execute()
        from_email = profile["emailAddress"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gmail error: {str(e)}")

    sent = []
    failed = []

    for draft in drafts:
        city = db.query(City).filter(City.id == draft.city_id).first()
        if not city:
            failed.append({"draft_id": draft.id, "error": "City not found"})
            continue

        recipient = draft.to_address or city.mayor_email or city.city_email
        if not recipient:
            failed.append({"draft_id": draft.id, "error": "No recipient address"})
            continue

        try:
            msg = _build_message(recipient, draft.subject, draft.body, from_email)
            result = service.users().messages().send(userId="me", body=msg).execute()

            # Mark draft sent
            draft.status = "sent"
            draft.sent_at = datetime.now(timezone.utc)

            # Log email
            email = Email(
                city_id=city.id,
                gmail_message_id=result.get("id"),
                gmail_thread_id=result.get("threadId"),
                direction="outbound",
                from_address=from_email,
                to_address=recipient,
                subject=draft.subject,
                body_preview=draft.body or "",
                sent_at=datetime.now(timezone.utc),
                is_draft=False,
                draft_type=draft.draft_type,
                draft_status="sent",
            )
            db.add(email)

            # Auto-advance city status
            new_status = STATUS_ADVANCE.get(draft.draft_type)
            if new_status and city.outreach_status not in ("in_conversation", "call_scheduled", "endorsed"):
                city.outreach_status = new_status

            city.last_contacted = datetime.now(timezone.utc)

            db.add(ActivityLog(
                city_id=city.id,
                action="email_sent",
                details=f"{draft.draft_type} sent to {recipient}",
            ))

            sent.append(draft.id)

        except Exception as e:
            failed.append({"draft_id": draft.id, "error": str(e)})

    db.commit()
    return {"sent": len(sent), "draft_ids": sent, "failed": failed}


class SyncResponse(BaseModel):
    synced: int
    matched: int
    unmatched: int


@router.post("/emails/sync", response_model=SyncResponse)
def sync_emails(db: Session = Depends(get_db)):
    if not gmail_client.is_connected(db):
        raise HTTPException(status_code=400, detail="Gmail not connected")

    try:
        service = gmail_client.get_gmail_service(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Get last sync time to avoid re-fetching everything
    last_synced = gmail_client.get_last_synced(db)
    query = "in:anywhere"
    if last_synced:
        # Gmail query uses epoch seconds
        from datetime import datetime
        dt = datetime.fromisoformat(last_synced.replace("Z", "+00:00"))
        epoch = int(dt.timestamp())
        query += f" after:{epoch}"

    try:
        result = service.users().messages().list(
            userId="me", q=query, maxResults=100
        ).execute()
        messages = result.get("messages", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gmail list error: {str(e)}")

    synced = matched = unmatched = 0

    for msg_ref in messages:
        msg_id = msg_ref["id"]

        # Skip if already stored
        existing = db.query(Email).filter(Email.gmail_message_id == msg_id).first()
        if existing:
            continue

        try:
            msg = service.users().messages().get(
                userId="me", id=msg_id, format="full"
            ).execute()
        except Exception:
            continue

        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        thread_id = msg.get("threadId")
        from_addr = headers.get("from", "")
        to_addr = headers.get("to", "")
        subject = headers.get("subject", "")
        date_str = headers.get("date", "")

        # Extract plain email from "Name <email>" format
        def extract_email(s):
            m = re.search(r'[\w.+-]+@[\w.-]+\.\w+', s)
            return m.group(0).lower() if m else s.lower()

        from_email = extract_email(from_addr)
        to_email = extract_email(to_addr)

        # Parse date
        sent_at = None
        try:
            from email.utils import parsedate_to_datetime
            sent_at = parsedate_to_datetime(date_str)
        except Exception:
            sent_at = datetime.now(timezone.utc)

        # Detect direction: if we sent it, it's outbound
        profile = service.users().getProfile(userId="me").execute()
        our_email = profile["emailAddress"].lower()
        direction = "outbound" if from_email == our_email else "inbound"

        # Extract body (full, no truncation)
        body_preview = _extract_body(msg.get("payload", {}))

        # Match to city
        city_id = _match_city(db, from_email, to_email, thread_id)

        email = Email(
            city_id=city_id,
            gmail_message_id=msg_id,
            gmail_thread_id=thread_id,
            direction=direction,
            from_address=from_addr,
            to_address=to_addr,
            subject=subject,
            body_preview=body_preview,
            sent_at=sent_at,
            is_draft=False,
            is_read=(direction == "outbound"),  # inbound starts unread
        )
        db.add(email)
        synced += 1
        if city_id:
            matched += 1
        else:
            unmatched += 1

    db.commit()
    gmail_client.set_last_synced(db)

    return SyncResponse(synced=synced, matched=matched, unmatched=unmatched)


def _extract_body(payload: dict) -> str:
    """Recursively extract plain text body from Gmail message payload."""
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if mime_type == "text/plain" and body_data:
        return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")

    if mime_type == "text/html" and body_data:
        html = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
        return re.sub(r'<[^>]+>', '', html)

    for part in payload.get("parts", []):
        result = _extract_body(part)
        if result:
            return result

    return ""


@router.get("/emails/unread-cities")
def get_unread_cities(db: Session = Depends(get_db)):
    rows = db.query(Email.city_id).filter(
        Email.is_read == False,
        Email.city_id.isnot(None),
    ).distinct().all()
    return {"city_ids": [r[0] for r in rows]}


@router.post("/emails/city/{city_id}/read")
def mark_city_emails_read(city_id: int, db: Session = Depends(get_db)):
    db.query(Email).filter(Email.city_id == city_id).update({"is_read": True})
    db.commit()
    return {"ok": True}


def _match_city(db: Session, from_email: str, to_email: str, thread_id: str | None) -> int | None:
    from models import City
    from sqlalchemy import or_, func

    # 1. Thread ID match — most reliable (reply to our outbound)
    if thread_id:
        existing = db.query(Email).filter(Email.gmail_thread_id == thread_id).first()
        if existing and existing.city_id:
            return existing.city_id

    # 2. Exact address match on city or mayor email
    for addr in [from_email, to_email]:
        city = db.query(City).filter(
            or_(
                func.lower(City.mayor_email) == addr,
                func.lower(City.city_email) == addr,
            )
        ).first()
        if city:
            return city.id

    # 3. Domain match against city_website
    domain = from_email.split("@")[-1] if "@" in from_email else None
    if domain and domain not in ("gmail.com", "yahoo.com", "outlook.com", "hotmail.com"):
        city = db.query(City).filter(City.city_website.ilike(f"%{domain}%")).first()
        if city:
            return city.id

    return None
