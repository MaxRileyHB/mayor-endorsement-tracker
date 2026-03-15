from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from typing import Optional, List
from datetime import datetime

import sys
sys.path.append("..")
from database import get_db
from models import City, ActivityLog, Email, CallLog
from schemas import CityRead, CityUpdate, BatchUpdate, StatsResponse, EmailRead, CallLogRead, CallLogCreate

router = APIRouter(prefix="/api/cities", tags=["cities"])

OUTREACH_STATUSES = [
    "no_contact_info", "city_contact_only", "info_requested",
    "ready_for_outreach", "outreach_sent", "in_conversation",
    "call_scheduled", "endorsed", "declined", "follow_up", "not_pursuing",
]


@router.get("/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)):
    total = db.query(City).count()

    by_status = {}
    for status in OUTREACH_STATUSES:
        by_status[status] = db.query(City).filter(City.outreach_status == status).count()

    by_tier = {}
    for tier in [1, 2, 3]:
        by_tier[str(tier)] = db.query(City).filter(City.outreach_tier == tier).count()

    return StatsResponse(
        total=total,
        by_status=by_status,
        by_tier=by_tier,
        endorsed=by_status.get("endorsed", 0),
        needs_verification=db.query(City).filter(City.mayor_needs_verification == True).count(),
        moratorium_active=db.query(City).filter(City.moratorium_active == True).count(),
    )


@router.get("/filter-options")
def get_filter_options(db: Session = Depends(get_db)):
    def distinct_simple(col):
        return sorted([r[0] for r in db.query(col).distinct().all() if r[0]])

    def distinct_districts(col):
        # Pull all distinct raw values, then split comma-separated entries in Python
        rows = db.query(col).filter(col.isnot(None)).distinct().all()
        nums = set()
        for (val,) in rows:
            for part in val.split(','):
                part = part.strip()
                if part.isdigit():
                    nums.add(str(int(part)))  # normalize "01" -> "1"
        return sorted(nums, key=int)

    return {
        "counties": distinct_simple(City.county),
        "senate_districts": distinct_districts(City.state_senate_district),
        "assembly_districts": distinct_districts(City.state_assembly_district),
        "congressional_districts": distinct_districts(City.congressional_district),
    }


@router.get("", response_model=List[CityRead])
def list_cities(
    search: Optional[str] = None,
    status: Optional[List[str]] = Query(default=None),
    tier: Optional[List[int]] = Query(default=None),
    county: Optional[List[str]] = Query(default=None),
    state_senate_district: Optional[List[str]] = Query(default=None),
    state_assembly_district: Optional[List[str]] = Query(default=None),
    congressional_district: Optional[List[str]] = Query(default=None),
    wildfire_risk_tier: Optional[List[str]] = Query(default=None),
    needs_verification: Optional[bool] = None,
    moratorium_active: Optional[bool] = None,
    is_distressed_county: Optional[bool] = None,
    has_undermarketed_zips: Optional[bool] = None,
    sort_by: str = "outreach_tier",
    sort_order: str = "asc",
    page: int = 1,
    per_page: int = 500,
    db: Session = Depends(get_db),
):
    q = db.query(City)

    if search:
        term = f"%{search}%"
        q = q.filter(or_(
            City.city_name.ilike(term),
            City.mayor.ilike(term),
            City.county.ilike(term),
        ))
    if status:
        q = q.filter(City.outreach_status.in_(status))
    if tier:
        q = q.filter(City.outreach_tier.in_(tier))
    if county:
        q = q.filter(City.county.in_(county))
    if state_senate_district:
        q = q.filter(or_(*[City.state_senate_district.op('~')(rf'(^|, ){d}(,|$)') for d in state_senate_district]))
    if state_assembly_district:
        q = q.filter(or_(*[City.state_assembly_district.op('~')(rf'(^|, ){d}(,|$)') for d in state_assembly_district]))
    if congressional_district:
        q = q.filter(or_(*[City.congressional_district.op('~')(rf'(^|, ){d}(,|$)') for d in congressional_district]))
    if wildfire_risk_tier:
        q = q.filter(City.wildfire_risk_tier.in_(wildfire_risk_tier))
    if needs_verification is not None:
        q = q.filter(City.mayor_needs_verification == needs_verification)
    if moratorium_active is not None:
        q = q.filter(City.moratorium_active == moratorium_active)
    if is_distressed_county is not None:
        q = q.filter(City.is_distressed_county == is_distressed_county)
    if has_undermarketed_zips is not None:
        q = q.filter(City.has_undermarketed_zips == has_undermarketed_zips)

    col = getattr(City, sort_by, City.city_name)
    q = q.order_by(col.asc() if sort_order == "asc" else col.desc())

    return q.offset((page - 1) * per_page).limit(per_page).all()


@router.get("/{city_id}", response_model=CityRead)
def get_city(city_id: int, db: Session = Depends(get_db)):
    city = db.query(City).filter(City.id == city_id).first()
    if not city:
        raise HTTPException(status_code=404, detail="City not found")
    return city


@router.patch("/{city_id}", response_model=CityRead)
def update_city(city_id: int, update: CityUpdate, db: Session = Depends(get_db)):
    city = db.query(City).filter(City.id == city_id).first()
    if not city:
        raise HTTPException(status_code=404, detail="City not found")

    old_status = city.outreach_status
    changes = []

    for field, value in update.model_dump(exclude_unset=True).items():
        if getattr(city, field) != value:
            changes.append(f"{field}: {getattr(city, field)} -> {value}")
            setattr(city, field, value)

    city.updated_at = datetime.utcnow()

    if changes:
        log = ActivityLog(
            city_id=city_id,
            action="updated",
            details="; ".join(changes),
        )
        db.add(log)

    db.commit()
    db.refresh(city)
    return city


@router.post("/batch-update")
def batch_update(payload: BatchUpdate, db: Session = Depends(get_db)):
    updates = payload.model_dump(exclude_unset=True, exclude={"city_ids"})
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updated = 0
    for city_id in payload.city_ids:
        city = db.query(City).filter(City.id == city_id).first()
        if not city:
            continue
        for field, value in updates.items():
            if value is not None:
                setattr(city, field, value)
        city.updated_at = datetime.utcnow()
        db.add(ActivityLog(
            city_id=city_id,
            action="batch_updated",
            details=str(updates),
        ))
        updated += 1

    db.commit()
    return {"updated": updated}


@router.get("/{city_id}/emails", response_model=List[EmailRead])
def get_city_emails(city_id: int, db: Session = Depends(get_db)):
    return (
        db.query(Email)
        .filter(Email.city_id == city_id)
        .order_by(Email.sent_at.asc())
        .all()
    )


@router.get("/{city_id}/calls", response_model=List[CallLogRead])
def get_city_calls(city_id: int, db: Session = Depends(get_db)):
    return (
        db.query(CallLog)
        .filter(CallLog.city_id == city_id)
        .order_by(CallLog.called_at.desc())
        .all()
    )


@router.post("/{city_id}/calls", response_model=CallLogRead)
def create_call_log(city_id: int, payload: CallLogCreate, db: Session = Depends(get_db)):
    city = db.query(City).filter(City.id == city_id).first()
    if not city:
        raise HTTPException(status_code=404, detail="City not found")
    call = CallLog(
        city_id=city_id,
        notes=payload.notes,
        outcome=payload.outcome,
        contact_type=payload.contact_type,
        called_at=payload.called_at or datetime.utcnow(),
    )
    db.add(call)
    city.last_contacted = datetime.utcnow()
    db.commit()
    db.refresh(call)
    return call


@router.delete("/{city_id}/calls/{call_id}", status_code=204)
def delete_call_log(city_id: int, call_id: int, db: Session = Depends(get_db)):
    call = db.query(CallLog).filter(CallLog.id == call_id, CallLog.city_id == city_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call log not found")
    db.delete(call)
    db.commit()


@router.get("/{city_id}/activity")
def get_activity(city_id: int, db: Session = Depends(get_db)):
    logs = (
        db.query(ActivityLog)
        .filter(ActivityLog.city_id == city_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(50)
        .all()
    )
    return logs
