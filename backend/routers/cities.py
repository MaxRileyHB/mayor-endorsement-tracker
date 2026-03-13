from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from typing import Optional, List
from datetime import datetime

import sys
sys.path.append("..")
from database import get_db
from models import City, ActivityLog
from schemas import CityRead, CityUpdate, BatchUpdate, StatsResponse

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


@router.get("", response_model=List[CityRead])
def list_cities(
    search: Optional[str] = None,
    status: Optional[str] = None,
    tier: Optional[int] = None,
    county: Optional[str] = None,
    needs_verification: Optional[bool] = None,
    moratorium_active: Optional[bool] = None,
    is_distressed_county: Optional[bool] = None,
    sort_by: str = "outreach_tier",
    sort_order: str = "asc",
    page: int = 1,
    per_page: int = 100,
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
        q = q.filter(City.outreach_status == status)
    if tier is not None:
        q = q.filter(City.outreach_tier == tier)
    if county:
        q = q.filter(City.county.ilike(f"%{county}%"))
    if needs_verification is not None:
        q = q.filter(City.mayor_needs_verification == needs_verification)
    if moratorium_active is not None:
        q = q.filter(City.moratorium_active == moratorium_active)
    if is_distressed_county is not None:
        q = q.filter(City.is_distressed_county == is_distressed_county)

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
