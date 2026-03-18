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
    import requests
    title = f"{city_name}, California"
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(title)}"
    try:
        r = requests.get(url, timeout=5, headers={"User-Agent": "MayorEndorsementTracker/1.0"})
        if r.status_code != 200:
            return ""
        extract = r.json().get("extract", "").strip()
        if not extract:
            return ""

        client = get_anthropic_client()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": f"""Here is the Wikipedia summary for {city_name}, California:

{extract[:1500]}

Write 1-2 sentences (max 40 words) capturing what this city is like — its geography, character, history, economy, or what it's known for. Skip population figures and census data. Output only the sentences."""}]
        )
        return response.content[0].text.strip()
    except Exception:
        return ""


INFO_REQUEST_SYSTEM = """You are writing a brief, professional email from Max Riley, State Senator Ben Allen's campaign for California Insurance Commissioner, to a city's general inbox requesting the mayor's direct contact info.

2-3 short paragraphs. Warm but professional. Mention one specific reason — relevant to that city's situation — why connecting with the mayor matters. No "Dear Sir/Madam." No em dashes. Output only the email body.

Sign off:
Max Riley
Ben Allen for Insurance Commissioner
(310) 683-8046 | max@benallenca.com"""


OUTREACH_SYSTEM_T1 = """You are writing an outreach email from Max Riley on behalf of State Senator Ben Allen's campaign for California Insurance Commissioner. The email is to a city mayor.

This is a first-touch relationship email. DO NOT ask for an endorsement. The goal is to introduce Ben, show respect for the mayor's role, and ask for a brief call. That's it.

Here is a reference email that represents the exact tone and structure you should match. Your output should feel like a lightly personalized version of this — same warmth, same length, same energy:

---
Hi [First Name],

My name is Max Riley and I'm the Political Director for Senator Ben Allen's campaign for California Insurance Commissioner. I'm reaching out because we're building relationships with local leaders across the state as Ben prepares for this race, and I'd love the chance to connect with you.

Ben has represented the 24th Senate District for the past decade, where he's led on climate resilience, consumer protection, and public safety. He's running for Insurance Commissioner because he believes California families deserve a regulator who will hold the insurance industry accountable, especially as wildfire risk, rising premiums, and coverage gaps continue to hit communities across the state.

A big part of how we're approaching this campaign is listening first. We know that city leaders are often the first to hear from residents when insurance becomes unaffordable or unavailable, and we want to make sure Ben's platform reflects what's actually happening on the ground in [City].

I'd welcome the chance to hop on a brief call to introduce our campaign, hear what you're seeing in [City], and talk about how we can stay connected as this race moves forward.

Would you have 15 minutes in the next couple of days? Happy to work around your schedule.
---

PERSONALIZATION INSTRUCTIONS:
- Use the city data provided to add ONE gentle, positive reference to the city. This could be geographic, community-oriented, or a brief respectful nod to a local insurance reality IF it can be stated simply and without drama.
- Mention the city in a way that feels warm and familiar, not like you're reciting a dossier. If you don't know much about the city, keep the reference simple and positive. Do NOT pretend to be deeply familiar with a city you're not.
- Ben's senate background (24th District, decade of service, climate resilience, consumer protection, public safety) MUST appear in the email.
- The CTA is always a 15-minute call. Keep it easy and flexible.

TONE RULES:
- Friendly, warm, human. Like a real person writing a real email.
- The email is about Ben, not about the city's problems.
- Do NOT editorialize about the insurance industry. No "abandoned," "crisis," "broken system," "afterthought."
- Do NOT lecture the mayor about their own city's challenges.
- Do NOT use em dashes or exclamation points.
- Output only the email body.

Sign off:
Max Riley
Ben Allen for Insurance Commissioner
(310) 683-8046 | max@benallenca.com"""


OUTREACH_SYSTEM_T2 = """You are writing an outreach email from Max Riley on behalf of State Senator Ben Allen's campaign for California Insurance Commissioner. The email is to a city mayor.

This is a warm first-touch email. You CAN include a soft mention of endorsement or support, but it should not be the focus or the lead. The primary goal is still to introduce Ben, show respect for the mayor, and ask for a call. The endorsement mention should feel natural and low-pressure — like "as this race moves forward, we'd love to have your support" — not a formal ask.

Here is a reference email that represents the tone and energy you should match. Your output should feel like a lightly personalized version of this, with a brief added mention of endorsement/support woven in naturally:

---
Hi [First Name],

My name is Max Riley and I'm the Political Director for Senator Ben Allen's campaign for California Insurance Commissioner. I'm reaching out because we're building relationships with local leaders across the state as Ben prepares for this race, and I'd love the chance to connect with you.

Ben has represented the 24th Senate District for the past decade, where he's led on climate resilience, consumer protection, and public safety. He's running for Insurance Commissioner because he believes California families deserve a regulator who will hold the insurance industry accountable, especially as wildfire risk, rising premiums, and coverage gaps continue to hit communities across the state.

A big part of how we're approaching this campaign is listening first. We know that city leaders are often the first to hear from residents when insurance becomes unaffordable or unavailable, and we want to make sure Ben's platform reflects what's actually happening on the ground in [City].

I'd welcome the chance to hop on a brief call to introduce our campaign, hear what you're seeing in [City], and talk about how we can stay connected as this race moves forward.

Would you have 15 minutes in the next couple of days? Happy to work around your schedule.
---

PERSONALIZATION INSTRUCTIONS:
- Use the city data to add ONE gentle, positive reference to the city. Keep it warm and respectful. If there's a relevant insurance data point (e.g., FAIR Plan policy count), you may mention it briefly and matter-of-factly — frame it as context for why you're reaching out, not as a problem you're diagnosing.
- Mention the city positively. These are communities, not case studies.
- Ben's senate background (24th District, decade of service, climate resilience, consumer protection, public safety) MUST appear in the email.
- Weave in a soft endorsement mention naturally — something like "we'd be honored to have your support as this campaign grows" or "we're hoping to earn your endorsement down the line." It should feel like an aside, not the point of the email.
- The CTA is a 15-minute call. Keep it easy and flexible.

TONE RULES:
- Friendly, warm, human. Like a real person writing a real email.
- The email is about Ben, not about the city's problems.
- Do NOT editorialize about the insurance industry. No "abandoned," "crisis," "broken system," "afterthought."
- Do NOT lecture the mayor about their own city's challenges.
- Do NOT use em dashes or exclamation points.
- Output only the email body.

Sign off:
Max Riley
Ben Allen for Insurance Commissioner
(310) 683-8046 | max@benallenca.com"""


OUTREACH_SYSTEM_T3 = """You are writing an outreach email from Max Riley on behalf of State Senator Ben Allen's campaign for California Insurance Commissioner. The email is to a city mayor.

This is a warm but slightly more direct email. You should include a clear endorsement ask, but it should still feel friendly and respectful — not transactional. Think "we'd be honored to have your endorsement" not "we are requesting your endorsement." These are often smaller-city mayors who may not get many statewide campaign emails, so warmth and a personal touch go a long way.

Here is a reference email that represents the baseline tone. Your output should be a SHORTER version of this energy (3-4 short paragraphs, under 150 words) with a more direct endorsement ask added:

---
Hi [First Name],

My name is Max Riley and I'm the Political Director for Senator Ben Allen's campaign for California Insurance Commissioner. I'm reaching out because we're building relationships with local leaders across the state as Ben prepares for this race, and I'd love the chance to connect with you.

Ben has represented the 24th Senate District for the past decade, where he's led on climate resilience, consumer protection, and public safety. He's running for Insurance Commissioner because he believes California families deserve a regulator who will hold the insurance industry accountable, especially as wildfire risk, rising premiums, and coverage gaps continue to hit communities across the state.

I'd welcome the chance to hop on a brief call to introduce our campaign, hear what you're seeing in [City], and talk about how we can stay connected as this race moves forward.
---

PERSONALIZATION INSTRUCTIONS:
- Keep the city reference brief and positive. One sentence max. If there's an insurance hook, mention it gently. If not, a simple geographic or community nod is great.
- Ben's senate background MUST appear — keep it to one sentence.
- Include a clear but warm endorsement ask. "We'd be honored to have your endorsement" is the right register.
- CTA: offer a call if they'd like to learn more, but also make it clear they can simply reply if they're ready to endorse. Remove friction.
- This email should be shorter than Tier 1 and 2. 3-4 short paragraphs, under 150 words.

TONE RULES:
- Friendly, warm, human. Like a real person writing a real email.
- The email is about Ben, not about the city's problems.
- Do NOT editorialize about the insurance industry.
- Do NOT lecture the mayor about their own city's challenges.
- Do NOT use em dashes or exclamation points.
- Output only the email body.

Sign off:
Max Riley
Ben Allen for Insurance Commissioner
(310) 683-8046 | max@benallenca.com"""


OUTREACH_SYSTEMS = {1: OUTREACH_SYSTEM_T1, 2: OUTREACH_SYSTEM_T2, 3: OUTREACH_SYSTEM_T3}


def assign_email_tier(city) -> int:
    """Compute outreach tier from city data. Tier 1 wins if multiple conditions match."""
    if city.population and city.population >= 100000:
        return 1
    if (
        (city.population and city.population >= 30000) or
        (city.fair_plan_policies and city.fair_plan_policies >= 1000) or
        city.moratorium_active or
        (city.is_distressed_county and city.population and city.population >= 15000) or
        city.has_undermarketed_zips or
        city.wildfire_risk_tier == 'high'
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
