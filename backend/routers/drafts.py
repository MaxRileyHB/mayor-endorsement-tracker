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


def fetch_wikipedia_blurb(city_name: str) -> str:
    import re, requests
    title = f"{city_name}, California"
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(title)}"
    try:
        r = requests.get(url, timeout=5, headers={"User-Agent": "MayorEndorsementTracker/1.0"})
        if r.status_code == 200:
            extract = r.json().get("extract", "")
            sentences = re.split(r'(?<=[.!?])\s+', extract.strip())
            return " ".join(sentences[:2])
    except Exception:
        pass
    return ""


INFO_REQUEST_SYSTEM = """You are writing a brief, professional email from Max Riley, State Senator Ben Allen's campaign for California Insurance Commissioner, to a city's general inbox requesting the mayor's direct contact info.

2-3 short paragraphs. Warm but professional. Mention one specific reason — relevant to that city's situation — why connecting with the mayor matters. No "Dear Sir/Madam." No em dashes. Output only the email body.

Sign off:
Max Riley
Ben Allen for Insurance Commissioner
(310) 683-8046 | max@benallenca.gov"""


OUTREACH_SYSTEM_T1 = """You are writing a concise outreach email from Max Riley, State Senator Ben Allen's campaign for California Insurance Commissioner, to a city mayor.

This is a Tier 1 mayor — a high-profile official in a major city. DO NOT ask for an endorsement in this email. The goal is to earn a conversation. These mayors get endorsement requests constantly and will ignore a cold ask from someone they don't know.

Instead, the frame is: Senator Allen is running for Insurance Commissioner, he's building his platform around issues that directly affect this mayor's city, and he wants to hear from mayors on the front lines of the insurance crisis before the election. You are offering the mayor a seat at the table, not asking for a favor.

Ben Allen's focus: FAIR Plan reform, insurance affordability, wildfire resilience, consumer protection.

3 short paragraphs:
1. Open with something specific to their city's insurance situation — make it clear you've done your homework and this isn't a mass email.
2. Explain that Senator Allen is talking to mayors across California to understand local insurance challenges and shape his platform. Position the mayor as someone whose perspective matters.
3. Close with a CTA offering a 15-minute call or meeting — keep it low-commitment. Something like "Would you have 15 minutes in the next couple weeks for a brief call?"

Warm, respectful, not salesy. No em dashes. Output only the email body.

Sign off:
Max Riley
Ben Allen for Insurance Commissioner
(310) 683-8046 | max@benallenca.gov"""


OUTREACH_SYSTEM_T2 = """You are writing a concise outreach email from Max Riley, State Senator Ben Allen's campaign for California Insurance Commissioner, to a city mayor.

This is a Tier 2 mayor — a mid-size city official whose community has real insurance challenges. The goal is to invite them into a coalition. You CAN mention the word "endorsement" but it should not be the lead. The frame is: Senator Allen is building a statewide coalition of mayors who understand the insurance crisis firsthand, and this mayor's city belongs in that coalition. The endorsement is presented as joining something meaningful, not doing a favor for a stranger.

Ben Allen's focus: FAIR Plan reform, insurance affordability, wildfire resilience, consumer protection.

3 short paragraphs:
1. Open with something specific to their city's insurance situation — a concrete number or fact that shows you know what their residents are dealing with.
2. Introduce Ben Allen briefly and explain he's building a coalition of mayors who are living the insurance crisis. Mention one specific credential or policy position. Frame the endorsement as "adding your city's voice to this effort" rather than a personal favor.
3. Close with a CTA — offer a brief call to discuss his platform and the endorsement, or let them know they can reach out directly. Make it easy to say yes.

Warm, direct, community-focused. No em dashes. Output only the email body.

Sign off:
Max Riley
Ben Allen for Insurance Commissioner
(310) 683-8046 | max@benallenca.gov"""


OUTREACH_SYSTEM_T3 = """You are writing a concise outreach email from Max Riley, State Senator Ben Allen's campaign for California Insurance Commissioner, to a city mayor.

This is a Tier 3 mayor — a smaller city where the mayor may not get many statewide endorsement requests. Be warm and respectful but get to the point. These mayors are often part-time officials who are busy and will appreciate brevity. Many will be flattered by a direct, personal ask and may say yes without needing a call.

Ben Allen's focus: FAIR Plan reform, insurance affordability, wildfire resilience, consumer protection.

3 short paragraphs:
1. Open with a brief, specific reference to their city — even one sentence showing you know something about the community. If there's an insurance hook (FAIR Plan reliance, wildfire risk), use it. If not, a quick geographic or community reference works.
2. Introduce Ben Allen in one sentence and make a clear, direct endorsement ask. Don't hedge. "We'd be honored to have your endorsement" is the right energy.
3. Close with a brief CTA — offer a call if they want to learn more, but make it clear they can also just reply to endorse. Remove friction.

Warm, direct, brief. No em dashes. Output only the email body.

Sign off:
Max Riley
Ben Allen for Insurance Commissioner
(310) 683-8046 | max@benallenca.gov"""


OUTREACH_SYSTEMS = {1: OUTREACH_SYSTEM_T1, 2: OUTREACH_SYSTEM_T2, 3: OUTREACH_SYSTEM_T3}


def assign_email_tier(city) -> int:
    """Compute outreach tier from city data. Tier 1 wins if multiple conditions match."""
    if city.population and city.population >= 100000:
        return 1
    if (
        (city.population and city.population >= 30000) or
        (city.fair_plan_policies and city.fair_plan_policies >= 1000) or
        city.moratorium_active or
        (city.is_distressed_county and city.population and city.population >= 15000)
    ):
        return 2
    return 3


def generate_draft_for_city(city: City, draft_type: str, batch_id: str, db: Session):
    client = _get_anthropic()

    # Get or fetch and cache Wikipedia blurb
    blurb = city.city_blurb
    if not blurb:
        blurb = fetch_wikipedia_blurb(city.city_name)
        if blurb:
            city.city_blurb = blurb
            db.add(city)
            db.commit()

    if draft_type == "info_request":
        to_address = city.city_email or ""
        context_parts = [f"City: {city.city_name}, {city.county} County"]
        if blurb:
            context_parts.append(f"Background: {blurb}")
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
        tier = city.outreach_tier or assign_email_tier(city)
        to_address = city.mayor_work_email or city.mayor_personal_email or city.mayor_email or city.city_email or ""
        context_parts = [f"City: {city.city_name}, {city.county} County"]
        if blurb:
            context_parts.append(f"Background: {blurb}")
        context_parts += [
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
        system = OUTREACH_SYSTEMS[tier]
        subject = {
            1: f"Insurance in {city.city_name} — Sen. Ben Allen",
            2: f"Sen. Ben Allen for Insurance Commissioner — {city.city_name}",
            3: f"Endorsement request — Ben Allen for Insurance Commissioner",
        }[tier]

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
        research_context={"city_name": city.city_name, "tier": tier if draft_type != "info_request" else (city.outreach_tier or assign_email_tier(city))},
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
