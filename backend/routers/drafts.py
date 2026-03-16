import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime

import sys
sys.path.append("..")
from database import get_db
from models import City, Draft, ActivityLog
from schemas import DraftRead, DraftUpdate

router = APIRouter(prefix="/api/drafts", tags=["drafts"])


def _get_anthropic():
    import anthropic
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


INFO_REQUEST_SYSTEM = """You are writing a brief, professional email on behalf of Max Riley from State Senator Ben Allen's campaign for California Insurance Commissioner. The email is being sent to a city's general email address to request the mayor's direct contact information.

Keep it to 3-4 short paragraphs. Be warm but professional. Mention one specific reason you want to connect with the mayor that is relevant to their city (e.g., wildfire risk, FAIR Plan reliance, insurance affordability). Sign off as Max Riley, Ben Allen for Insurance Commissioner.

Do NOT use overly formal language. Do NOT use "Dear Sir/Madam." Do use the mayor's name if known. Do NOT use em dashes. Do NOT include a subject line in the body — output only the email body text itself.

Sign off with this exact signature:
Max Riley
Ben Allen for Insurance Commissioner
(310) 683-8046 | max@benallenca.gov"""


OUTREACH_SYSTEM = """You are writing a personalized endorsement outreach email on behalf of Max Riley from State Senator Ben Allen's campaign for California Insurance Commissioner. The email is to a city mayor requesting their endorsement.

Key messaging pillars for Ben Allen:
- FAIR Plan reform and stabilization
- Insurance affordability and availability for homeowners
- Wildfire resilience and community preparedness
- Consumer protection and rate transparency
- Ben's legislative record on insurance and environmental issues as a State Senator

Keep it to 4-5 short paragraphs. Be warm, direct, and specific. Reference concrete data about the city's insurance situation. Make a clear ask for the endorsement. Offer a phone call to discuss further.

Do NOT be wonky or overly policy-heavy. DO make it feel personal and specific to their city. Do NOT use em dashes. Do NOT include a subject line in the body — output only the email body text itself.

Sign off with this exact signature:
Max Riley
Ben Allen for Insurance Commissioner
(310) 683-8046 | max@benallenca.gov"""


def generate_draft_for_city(city: City, draft_type: str, batch_id: str, db: Session):
    client = _get_anthropic()

    if draft_type == "info_request":
        to_address = city.city_email or ""
        context_parts = [f"City: {city.city_name}, {city.county} County"]
        if city.mayor:
            context_parts.append(f"Mayor: {city.mayor}")
        if city.moratorium_active and city.moratorium_fires:
            fires = ", ".join(city.moratorium_fires) if isinstance(city.moratorium_fires, list) else str(city.moratorium_fires)
            context_parts.append(f"Active insurance moratorium (fires: {fires})")
        if city.fair_plan_policies and city.fair_plan_policies > 0:
            context_parts.append(f"FAIR Plan policies: {city.fair_plan_policies:,}")
        if city.is_distressed_county:
            context_parts.append("Located in CDI-designated distressed county")

        user_prompt = "\n".join(context_parts)
        system = INFO_REQUEST_SYSTEM
        subject = f"Request for Mayor's Contact Information — Ben Allen for Insurance Commissioner"

    else:  # endorsement_outreach
        to_address = city.mayor_work_email or city.mayor_personal_email or city.mayor_email or city.city_email or ""
        context_parts = [
            f"City: {city.city_name}, {city.county} County",
            f"Population: {city.population:,}" if city.population else "",
            f"Mayor: {city.mayor}" if city.mayor else "",
            f"FAIR Plan policies: {city.fair_plan_policies:,}" if city.fair_plan_policies else "",
            f"FAIR Plan exposure: ${city.fair_plan_exposure:,}" if city.fair_plan_exposure else "",
            f"Wildfire risk tier: {city.wildfire_risk_tier}" if city.wildfire_risk_tier else "",
            "CDI-designated distressed county" if city.is_distressed_county else "",
            "Has undermarketed ZIP codes" if city.has_undermarketed_zips else "",
        ]
        if city.moratorium_active and city.moratorium_fires:
            fires = ", ".join(city.moratorium_fires) if isinstance(city.moratorium_fires, list) else str(city.moratorium_fires)
            context_parts.append(f"Active insurance moratorium — fires: {fires}")

        user_prompt = "\n".join(p for p in context_parts if p)
        system = OUTREACH_SYSTEM
        subject = f"Endorsement Request — Ben Allen for California Insurance Commissioner"

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=600,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        body = response.content[0].text.strip()
        import re as _re
        # Strip subject line if the AI included one despite instructions
        body = _re.sub(r'^Subject:[^\n]*\n\n?', '', body, flags=_re.IGNORECASE).strip()
        # Normalize line endings
        body = body.replace('\r\n', '\n').replace('\r', '\n')
    except Exception as e:
        body = f"[Generation failed: {e}]"

    draft = Draft(
        city_id=city.id,
        draft_type=draft_type,
        to_address=to_address,
        subject=subject,
        body=body,
        status="pending_review",
        batch_id=batch_id,
        research_context={"city_name": city.city_name, "tier": city.outreach_tier},
    )
    db.add(draft)
    db.commit()


def _run_batch(city_ids: list, draft_type: str, batch_id: str):
    from database import SessionLocal
    db = SessionLocal()
    try:
        for city_id in city_ids:
            city = db.query(City).filter(City.id == city_id).first()
            if city:
                generate_draft_for_city(city, draft_type, batch_id, db)
    finally:
        db.close()


@router.post("/generate")
def generate_drafts(
    payload: dict,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    city_ids = payload.get("city_ids", [])
    draft_type = payload.get("draft_type", "info_request")
    if not city_ids:
        raise HTTPException(status_code=400, detail="No city_ids provided")

    batch_id = str(uuid.uuid4())[:8]
    background_tasks.add_task(_run_batch, city_ids, draft_type, batch_id)
    return {"batch_id": batch_id, "city_count": len(city_ids), "status": "generating"}


@router.get("", response_model=List[DraftRead])
def list_drafts(
    batch_id: Optional[str] = None,
    city_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Draft, City.city_name).join(City, Draft.city_id == City.id, isouter=True)
    if batch_id:
        q = q.filter(Draft.batch_id == batch_id)
    if city_id:
        q = q.filter(Draft.city_id == city_id)
    if status:
        q = q.filter(Draft.status == status)
    rows = q.order_by(Draft.created_at.desc()).all()

    results = []
    for draft, city_name in rows:
        d = DraftRead.model_validate(draft)
        d.city_name = city_name
        results.append(d)
    return results


@router.patch("/{draft_id}", response_model=DraftRead)
def update_draft(draft_id: int, update: DraftUpdate, db: Session = Depends(get_db)):
    draft = db.query(Draft).filter(Draft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(draft, field, value)
    if update.status in ("approved", "rejected", "edited"):
        draft.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(draft)
    row = db.query(Draft, City.city_name).join(City, Draft.city_id == City.id, isouter=True).filter(Draft.id == draft_id).first()
    result = DraftRead.model_validate(row[0])
    result.city_name = row[1]
    return result


@router.post("/{draft_id}/regenerate")
def regenerate_draft(draft_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    draft = db.query(Draft).filter(Draft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    draft.status = "rejected"
    db.commit()
    batch_id = str(uuid.uuid4())[:8]
    background_tasks.add_task(_run_batch, [draft.city_id], draft.draft_type, batch_id)
    return {"batch_id": batch_id, "status": "generating"}


@router.get("/batch/{batch_id}/status")
def batch_status(batch_id: str, db: Session = Depends(get_db)):
    drafts = db.query(Draft).filter(Draft.batch_id == batch_id).all()
    by_status = {}
    for d in drafts:
        by_status[d.status] = by_status.get(d.status, 0) + 1
    return {"batch_id": batch_id, "total": len(drafts), "by_status": by_status}
