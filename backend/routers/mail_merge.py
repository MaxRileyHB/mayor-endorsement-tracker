"""
Mail Merge router for Mayor Endorsement CRM.

Handles template CRUD, recipient filtering, preview, test sends,
and async staggered batch sending with pause / resume / cancel.
"""

import base64
import re
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
import email.policy
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_

from database import get_db, SessionLocal
from models import City, Email, ActivityLog, MailMergeTemplate, MailMergeJob
import gmail_client
from sheets_sync import schedule_sync

router = APIRouter(prefix="/api/mail-merge", tags=["mail-merge"])

FROM_NAME = "Max Riley - Ben Allen for Insurance Commissioner"

# ── Field tag definitions ─────────────────────────────────────────────────────

def _first_name(name: str) -> str:
    if not name:
        return ""
    # Handle "Last, First" format
    if "," in name:
        parts = name.split(",", 1)
        rest = parts[1].strip()
        return rest.split()[0] if rest else parts[0].strip()
    return name.strip().split()[0]


FIELD_TAGS = {
    "mayor_first_name": lambda c: _first_name(c.mayor or ""),
    "mayor_full_name":  lambda c: c.mayor or "",
    "city_name":        lambda c: c.city_name or "",
    "county":           lambda c: c.county or "",
    "population":       lambda c: f"{c.population:,}" if c.population else "",
    "mayor_title":      lambda c: "Mayor",
    "city_website":     lambda c: c.city_website or "",
}

AVAILABLE_TAGS = list(FIELD_TAGS.keys())


def _resolve(template: str, city: City) -> tuple[str, list[str]]:
    """Replace {tag} placeholders in an HTML template string.
    Returns (resolved_html, list_of_tags_that_resolved_to_empty).
    """
    empty_tags: list[str] = []

    def replacer(m: re.Match) -> str:
        tag = m.group(1)
        resolver = FIELD_TAGS.get(tag)
        if resolver is None:
            return m.group(0)   # keep unknown tags unchanged
        value = resolver(city)
        if not value:
            empty_tags.append(tag)
        return value

    resolved = re.sub(r'\{([^}]+)\}', replacer, template)
    return resolved, empty_tags


# ── Pydantic models ───────────────────────────────────────────────────────────

class TemplateCreate(BaseModel):
    name: str
    subject_template: str
    body_template: str


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    subject_template: Optional[str] = None
    body_template: Optional[str] = None


class MergeFilters(BaseModel):
    city_ids: list[int] = []           # if non-empty, ignores all other filters
    statuses: list[str] = []
    tiers: list[int] = []
    counties: list[str] = []
    wildfire_risk: list[str] = []
    contact_filter: str = ""           # "has_mayor_email" | "has_any_email" | "no_email" | ""
    last_contacted_filter: str = ""    # "never" | "not_in_X_days" | "in_X_days" | ""
    last_contacted_days: int = 14
    exclude_endorsed: bool = True
    exclude_declined: bool = True
    exclude_not_pursuing: bool = True


class CountRequest(BaseModel):
    filters: MergeFilters
    email_priority: list[str] = ["mayor_work", "mayor_personal", "city"]


class PreviewRequest(BaseModel):
    template_id: int
    filters: MergeFilters
    email_priority: list[str] = ["mayor_work", "mayor_personal", "city"]
    count: int = 5


class TestRequest(BaseModel):
    template_id: int
    city_id: int
    test_email: str


class SendRequest(BaseModel):
    template_id: int
    filters: MergeFilters
    email_priority: list[str] = ["mayor_work", "mayor_personal", "city"]
    stagger_rate: str = "normal"    # "fast" | "normal" | "slow"


# ── Filtering helpers ─────────────────────────────────────────────────────────

def _apply_filters(db: Session, filters: MergeFilters) -> list[City]:
    q = db.query(City)

    if filters.city_ids:
        q = q.filter(City.id.in_(filters.city_ids))
    else:
        if filters.statuses:
            q = q.filter(City.outreach_status.in_(filters.statuses))
        if filters.tiers:
            q = q.filter(City.outreach_tier.in_(filters.tiers))
        if filters.counties:
            q = q.filter(City.county.in_(filters.counties))
        if filters.wildfire_risk:
            q = q.filter(City.wildfire_risk_tier.in_(filters.wildfire_risk))
        if filters.exclude_endorsed:
            q = q.filter(City.outreach_status != "endorsed")
        if filters.exclude_declined:
            q = q.filter(City.outreach_status != "declined")
        if filters.exclude_not_pursuing:
            q = q.filter(City.outreach_status != "not_pursuing")

        now = datetime.now(timezone.utc)
        lf = filters.last_contacted_filter
        days = filters.last_contacted_days
        if lf == "never":
            q = q.filter(City.last_contacted.is_(None))
        elif lf == "not_in_X_days":
            cutoff = now - timedelta(days=days)
            q = q.filter(or_(City.last_contacted.is_(None), City.last_contacted < cutoff))
        elif lf == "in_X_days":
            cutoff = now - timedelta(days=days)
            q = q.filter(City.last_contacted >= cutoff)

        cf = filters.contact_filter
        if cf == "has_mayor_email":
            q = q.filter(or_(
                City.mayor_work_email.isnot(None),
                City.mayor_personal_email.isnot(None),
            ))
        elif cf == "has_any_email":
            q = q.filter(or_(
                City.mayor_work_email.isnot(None),
                City.mayor_personal_email.isnot(None),
                City.city_email.isnot(None),
            ))
        elif cf == "no_email":
            q = q.filter(
                City.mayor_work_email.is_(None),
                City.mayor_personal_email.is_(None),
                City.city_email.is_(None),
            )

    return q.order_by(City.city_name.asc()).all()


def _resolve_email(city: City, priority: list[str]) -> tuple[str | None, str | None]:
    """Return (email_address, source_key) using the priority cascade."""
    field_map = {
        "mayor_work":     city.mayor_work_email,
        "mayor_personal": city.mayor_personal_email,
        "city":           city.city_email,
    }
    for field in priority:
        val = field_map.get(field)
        if val:
            return val, field
    return None, None


def _build_plan(cities: list[City], email_priority: list[str]) -> tuple[list[dict], list[dict]]:
    """Build the send plan and skipped list from a list of cities."""
    plan: list[dict] = []
    skipped: list[dict] = []

    for city in cities:
        if not city.mayor:
            skipped.append({
                "city_id": city.id,
                "city_name": city.city_name,
                "reason": "no mayor name",
            })
            continue

        to_email, source = _resolve_email(city, email_priority)
        if not to_email:
            skipped.append({
                "city_id": city.id,
                "city_name": city.city_name,
                "reason": "no email address",
            })
            continue

        plan.append({
            "city_id":      city.id,
            "city_name":    city.city_name,
            "mayor_name":   city.mayor,
            "to_email":     to_email,
            "email_source": source,
        })

    return plan, skipped


def _email_breakdown(plan: list[dict], skipped: list[dict]) -> dict:
    counts = Counter(item["email_source"] for item in plan)
    no_email = sum(1 for s in skipped if s["reason"] == "no email address")
    return {
        "mayor_work":    counts.get("mayor_work", 0),
        "mayor_personal": counts.get("mayor_personal", 0),
        "city":          counts.get("city", 0),
        "no_email":      no_email,
    }


# ── Email building ────────────────────────────────────────────────────────────

def _build_html_message(to: str, subject: str, body_html: str, from_email: str) -> dict:
    """Build a Gmail API raw message from an HTML body (TipTap output)."""
    wrapped = (
        '<html><body style="margin:0;padding:0;font-family:Arial,sans-serif;'
        'font-size:14px;line-height:1.6;">'
        + body_html.strip()
        + '</body></html>'
    )
    plain = re.sub(r'<[^>]+>', '', wrapped).strip()

    msg = EmailMessage(policy=email.policy.SMTP)
    msg['From'] = f"{FROM_NAME} <{from_email}>"
    msg['To'] = to
    msg['Subject'] = subject
    msg.set_content(plain, charset='utf-8')
    msg.add_alternative(wrapped, subtype='html', charset='utf-8')

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {"raw": raw}


# ── Async job state ───────────────────────────────────────────────────────────

_job_controls: dict[str, dict] = {}   # job_id → {paused: bool, cancelled: bool}
_job_lock = threading.Lock()

STAGGER_RATES = {"fast": 10, "normal": 30, "slow": 60}


def _run_job(job_id: str) -> None:
    controls = _job_controls.get(job_id, {})

    # Load job and template once
    db = SessionLocal()
    try:
        job = db.query(MailMergeJob).filter(MailMergeJob.id == job_id).first()
        if not job:
            return
        template = db.query(MailMergeTemplate).filter(
            MailMergeTemplate.id == job.template_id
        ).first()
        city_plan = list(job.city_plan or [])
        stagger = job.stagger_seconds
    finally:
        db.close()

    # Get Gmail service once (handles token refresh)
    db = SessionLocal()
    try:
        if not gmail_client.is_connected(db):
            db.query(MailMergeJob).filter(MailMergeJob.id == job_id).update({
                "status": "cancelled",
                "completed_at": datetime.now(timezone.utc),
            })
            db.commit()
            return
        service = gmail_client.get_gmail_service(db)
        profile = service.users().getProfile(userId="me").execute()
        from_email = profile["emailAddress"]
    except Exception as exc:
        print(f"[mail_merge] Gmail init error: {exc}")
        db.query(MailMergeJob).filter(MailMergeJob.id == job_id).update({
            "status": "cancelled",
            "completed_at": datetime.now(timezone.utc),
        })
        db.commit()
        return
    finally:
        db.close()

    for i, item in enumerate(city_plan):
        if controls.get("cancelled"):
            break

        # Respect pause
        while controls.get("paused") and not controls.get("cancelled"):
            time.sleep(1)
        if controls.get("cancelled"):
            break

        city_id = item["city_id"]
        to_email = item["to_email"]
        email_source = item["email_source"]

        db = SessionLocal()
        try:
            city = db.query(City).filter(City.id == city_id).first()
            if not city:
                job_obj = db.query(MailMergeJob).filter(MailMergeJob.id == job_id).first()
                if job_obj:
                    job_obj.failed += 1
                    db.commit()
                continue

            # Update "currently sending to" display
            job_obj = db.query(MailMergeJob).filter(MailMergeJob.id == job_id).first()
            if job_obj:
                job_obj.current_city = f"{city.city_name} ({city.mayor or 'Unknown'})"
                db.commit()

            subject, _ = _resolve(template.subject_template, city)
            body, _ = _resolve(template.body_template, city)

            try:
                msg = _build_html_message(to_email, subject, body, from_email)
                result = service.users().messages().send(userId="me", body=msg).execute()

                # Log email
                db.add(Email(
                    city_id=city_id,
                    gmail_message_id=result.get("id"),
                    gmail_thread_id=result.get("threadId"),
                    direction="outbound",
                    from_address=from_email,
                    to_address=to_email,
                    subject=subject,
                    body_preview=re.sub(r'<[^>]+>', '', body)[:500],
                    sent_at=datetime.now(timezone.utc),
                    is_draft=False,
                    draft_type="mail_merge",
                    draft_status="sent",
                ))

                # Auto-advance city status
                if city.outreach_status == "ready_for_outreach":
                    city.outreach_status = "outreach_sent"
                elif (
                    city.outreach_status in ("no_contact_info", "city_contact_only")
                    and email_source == "city"
                ):
                    city.outreach_status = "info_requested"

                city.last_contacted = datetime.now(timezone.utc)

                db.add(ActivityLog(
                    city_id=city_id,
                    action="mail_merge_sent",
                    details=f"Mail merge sent to {to_email}",
                ))

                job_obj = db.query(MailMergeJob).filter(MailMergeJob.id == job_id).first()
                if job_obj:
                    job_obj.sent += 1
                db.commit()

            except Exception as exc:
                print(f"[mail_merge] send error city {city_id}: {exc}")
                job_obj = db.query(MailMergeJob).filter(MailMergeJob.id == job_id).first()
                if job_obj:
                    job_obj.failed += 1
                db.commit()

        except Exception as exc:
            print(f"[mail_merge] job loop error: {exc}")
        finally:
            db.close()

        # Stagger delay (not after the last email)
        if i < len(city_plan) - 1 and not controls.get("cancelled"):
            time.sleep(stagger)

    # Finalize job
    db = SessionLocal()
    try:
        final_status = "cancelled" if controls.get("cancelled") else "completed"
        job_obj = db.query(MailMergeJob).filter(MailMergeJob.id == job_id).first()
        if job_obj:
            job_obj.status = final_status
            job_obj.completed_at = datetime.now(timezone.utc)
            job_obj.current_city = None
            db.commit()
        if final_status == "completed":
            schedule_sync()
    finally:
        db.close()

    with _job_lock:
        _job_controls.pop(job_id, None)


# ── Template CRUD ─────────────────────────────────────────────────────────────

@router.get("/tags")
def list_tags():
    return {"tags": AVAILABLE_TAGS}


@router.post("/templates")
def create_template(payload: TemplateCreate, db: Session = Depends(get_db)):
    t = MailMergeTemplate(
        name=payload.name,
        subject_template=payload.subject_template,
        body_template=payload.body_template,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.get("/templates")
def list_templates(db: Session = Depends(get_db)):
    return db.query(MailMergeTemplate).order_by(MailMergeTemplate.updated_at.desc()).all()


@router.get("/templates/{template_id}")
def get_template(template_id: int, db: Session = Depends(get_db)):
    t = db.query(MailMergeTemplate).filter(MailMergeTemplate.id == template_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return t


@router.patch("/templates/{template_id}")
def update_template(template_id: int, payload: TemplateUpdate, db: Session = Depends(get_db)):
    t = db.query(MailMergeTemplate).filter(MailMergeTemplate.id == template_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    if payload.name is not None:
        t.name = payload.name
    if payload.subject_template is not None:
        t.subject_template = payload.subject_template
    if payload.body_template is not None:
        t.body_template = payload.body_template
    t.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(t)
    return t


@router.delete("/templates/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db)):
    t = db.query(MailMergeTemplate).filter(MailMergeTemplate.id == template_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    db.delete(t)
    db.commit()
    return {"ok": True}


# ── Count & Preview ───────────────────────────────────────────────────────────

@router.post("/count")
def count_recipients(payload: CountRequest, db: Session = Depends(get_db)):
    """Fast recipient count + email source breakdown. Called live as filters change."""
    cities = _apply_filters(db, payload.filters)
    plan, skipped = _build_plan(cities, payload.email_priority)
    breakdown = _email_breakdown(plan, skipped)
    return {
        "total_matched": len(cities),
        "will_send":     len(plan),
        "skipped":       len(skipped),
        "no_email":      breakdown["no_email"],
        "no_mayor_name": sum(1 for s in skipped if s["reason"] == "no mayor name"),
        "breakdown":     breakdown,
        "city_names":    [c.city_name for c in cities],
    }


@router.post("/preview")
def preview_merge(payload: PreviewRequest, db: Session = Depends(get_db)):
    """Return up to `count` merged preview cards from the filtered city list."""
    import random

    template = db.query(MailMergeTemplate).filter(
        MailMergeTemplate.id == payload.template_id
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    cities = _apply_filters(db, payload.filters)
    plan, skipped = _build_plan(cities, payload.email_priority)

    sample = random.sample(plan, min(payload.count, len(plan)))
    previews = []

    for item in sample:
        city = db.query(City).filter(City.id == item["city_id"]).first()
        if not city:
            continue
        subject, subj_empty = _resolve(template.subject_template, city)
        body, body_empty    = _resolve(template.body_template, city)
        previews.append({
            "city_id":      city.id,
            "city_name":    city.city_name,
            "status":       city.outreach_status,
            "to_email":     item["to_email"],
            "email_source": item["email_source"],
            "subject":      subject,
            "body":         body,
            "empty_tags":   list(set(subj_empty + body_empty)),
        })

    # Count missing tags across ALL cities in the plan (sample a subset for speed)
    check_sample = random.sample(plan, min(50, len(plan)))
    tag_missing: dict[str, int] = {}
    for item in check_sample:
        city = db.query(City).filter(City.id == item["city_id"]).first()
        if not city:
            continue
        _, se = _resolve(template.subject_template, city)
        _, be = _resolve(template.body_template, city)
        for tag in set(se + be):
            tag_missing[tag] = tag_missing.get(tag, 0) + 1

    return {
        "previews":           previews,
        "total_will_send":    len(plan),
        "total_skipped":      len(skipped),
        "tag_missing_counts": tag_missing,
        "skipped_cities":     skipped[:20],
    }


# ── Test send ─────────────────────────────────────────────────────────────────

@router.post("/test")
def send_test(payload: TestRequest, db: Session = Depends(get_db)):
    if not gmail_client.is_connected(db):
        raise HTTPException(status_code=400, detail="Gmail not connected")

    template = db.query(MailMergeTemplate).filter(
        MailMergeTemplate.id == payload.template_id
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    city = db.query(City).filter(City.id == payload.city_id).first()
    if not city:
        raise HTTPException(status_code=404, detail="City not found")

    try:
        service = gmail_client.get_gmail_service(db)
        profile = service.users().getProfile(userId="me").execute()
        from_email = profile["emailAddress"]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gmail error: {exc}")

    subject, _ = _resolve(template.subject_template, city)
    body, _     = _resolve(template.body_template, city)

    banner = (
        '<div style="background:#FFF3CD;border:1px solid #FFC107;border-radius:4px;'
        'padding:8px 12px;margin-bottom:16px;font-size:12px;color:#856404;">'
        f'<strong>TEST EMAIL</strong> — using data from <em>{city.city_name}</em>'
        '</div>'
    )

    try:
        msg = _build_html_message(
            payload.test_email,
            f"[TEST] {subject}",
            banner + body,
            from_email,
        )
        service.users().messages().send(userId="me", body=msg).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Send error: {exc}")

    return {"ok": True, "sent_to": payload.test_email}


# ── Batch send ────────────────────────────────────────────────────────────────

@router.post("/send")
def start_send(payload: SendRequest, db: Session = Depends(get_db)):
    if not gmail_client.is_connected(db):
        raise HTTPException(status_code=400, detail="Gmail not connected")

    template = db.query(MailMergeTemplate).filter(
        MailMergeTemplate.id == payload.template_id
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    cities = _apply_filters(db, payload.filters)
    plan, skipped = _build_plan(cities, payload.email_priority)

    if not plan:
        raise HTTPException(status_code=400, detail="No cities to send to after filtering")

    stagger = STAGGER_RATES.get(payload.stagger_rate, 30)
    job_id = str(uuid.uuid4())

    job = MailMergeJob(
        id=job_id,
        template_id=template.id,
        status="running",
        total=len(plan),
        sent=0,
        skipped=len(skipped),
        failed=0,
        stagger_seconds=stagger,
        city_plan=plan,
        skipped_cities=skipped,
    )
    db.add(job)
    db.commit()

    with _job_lock:
        _job_controls[job_id] = {"paused": False, "cancelled": False}

    thread = threading.Thread(target=_run_job, args=(job_id,), daemon=True)
    thread.start()

    estimated_minutes = round((len(plan) * stagger) / 60, 1)
    return {
        "job_id":           job_id,
        "total_count":      len(plan),
        "skipped_count":    len(skipped),
        "skipped_cities":   skipped[:20],
        "estimated_minutes": estimated_minutes,
    }


@router.get("/send/{job_id}")
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.query(MailMergeJob).filter(MailMergeJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    remaining = max(job.total - job.sent - job.failed, 0)
    est_remaining = round((remaining * job.stagger_seconds) / 60, 1)

    return {
        "job_id":                      job.id,
        "status":                      job.status,
        "total":                       job.total,
        "sent":                        job.sent,
        "skipped":                     job.skipped,
        "failed":                      job.failed,
        "current_city":                job.current_city,
        "estimated_remaining_minutes": est_remaining,
        "created_at":                  job.created_at,
        "completed_at":                job.completed_at,
    }


@router.post("/send/{job_id}/pause")
def pause_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(MailMergeJob).filter(MailMergeJob.id == job_id).first()
    if not job or job.status != "running":
        raise HTTPException(status_code=400, detail="Job is not running")

    with _job_lock:
        if job_id in _job_controls:
            _job_controls[job_id]["paused"] = True

    job.status = "paused"
    db.commit()
    return {"ok": True}


@router.post("/send/{job_id}/resume")
def resume_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(MailMergeJob).filter(MailMergeJob.id == job_id).first()
    if not job or job.status != "paused":
        raise HTTPException(status_code=400, detail="Job is not paused")

    with _job_lock:
        if job_id not in _job_controls:
            raise HTTPException(
                status_code=400,
                detail="Job thread is no longer active (server may have restarted)",
            )
        _job_controls[job_id]["paused"] = False

    job.status = "running"
    db.commit()
    return {"ok": True}


@router.post("/send/{job_id}/cancel")
def cancel_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(MailMergeJob).filter(MailMergeJob.id == job_id).first()
    if not job or job.status in ("completed", "cancelled"):
        raise HTTPException(status_code=400, detail="Job is already finished")

    with _job_lock:
        if job_id in _job_controls:
            _job_controls[job_id]["cancelled"] = True
        else:
            # Thread died (e.g. server restart) — mark directly
            job.status = "cancelled"
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            return {"ok": True}

    job.status = "cancelled"
    db.commit()
    return {"ok": True}
