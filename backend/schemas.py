from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime, date


class CityBase(BaseModel):
    city_name: str
    county: Optional[str] = None
    population: Optional[int] = None
    mayor: Optional[str] = None
    mayor_pro_tem: Optional[str] = None
    previous_mayor: Optional[str] = None
    mayor_needs_verification: Optional[bool] = False
    council_members: Optional[Any] = None
    city_manager: Optional[str] = None
    city_clerk: Optional[str] = None
    city_attorney: Optional[str] = None
    city_address: Optional[str] = None
    city_phone: Optional[str] = None
    city_fax: Optional[str] = None
    city_website: Optional[str] = None
    city_email: Optional[str] = None
    office_hours: Optional[str] = None
    mayor_email: Optional[str] = None
    mayor_phone: Optional[str] = None
    mayor_contact_source: Optional[str] = None
    congressional_district: Optional[str] = None
    state_senate_district: Optional[str] = None
    state_assembly_district: Optional[str] = None
    party_affiliation: Optional[str] = None
    fair_plan_policies: Optional[int] = 0
    fair_plan_exposure: Optional[int] = 0
    is_distressed_county: Optional[bool] = False
    has_undermarketed_zips: Optional[bool] = False
    moratorium_fires: Optional[Any] = None
    moratorium_active: Optional[bool] = False
    wildfire_risk_tier: Optional[str] = None
    outreach_status: Optional[str] = "no_contact_info"
    outreach_tier: Optional[int] = 3
    last_contacted: Optional[datetime] = None
    next_action: Optional[str] = None
    next_action_date: Optional[date] = None
    notes: Optional[str] = None
    incorporated_date: Optional[str] = None


class CityRead(CityBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CityUpdate(BaseModel):
    """Partial update — all fields optional."""
    mayor: Optional[str] = None
    mayor_pro_tem: Optional[str] = None
    mayor_needs_verification: Optional[bool] = None
    mayor_email: Optional[str] = None
    mayor_phone: Optional[str] = None
    mayor_contact_source: Optional[str] = None
    city_email: Optional[str] = None
    city_phone: Optional[str] = None
    city_website: Optional[str] = None
    outreach_status: Optional[str] = None
    outreach_tier: Optional[int] = None
    next_action: Optional[str] = None
    next_action_date: Optional[date] = None
    notes: Optional[str] = None
    party_affiliation: Optional[str] = None


class BatchUpdate(BaseModel):
    city_ids: List[int]
    outreach_status: Optional[str] = None
    outreach_tier: Optional[int] = None


class StatsResponse(BaseModel):
    total: int
    by_status: dict
    by_tier: dict
    endorsed: int
    needs_verification: int
    moratorium_active: int


class DraftRead(BaseModel):
    id: int
    city_id: int
    city_name: Optional[str] = None
    draft_type: str
    to_address: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    status: str
    batch_id: Optional[str] = None
    research_context: Optional[Any] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class EmailRead(BaseModel):
    id: int
    city_id: int
    direction: Optional[str] = None
    from_address: Optional[str] = None
    to_address: Optional[str] = None
    subject: Optional[str] = None
    body_preview: Optional[str] = None
    sent_at: Optional[datetime] = None
    is_draft: Optional[bool] = False
    draft_type: Optional[str] = None
    draft_status: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CallLogCreate(BaseModel):
    notes: Optional[str] = None
    outcome: Optional[str] = None
    contact_type: Optional[str] = None
    called_at: Optional[datetime] = None


class CallLogRead(BaseModel):
    id: int
    city_id: int
    notes: Optional[str] = None
    outcome: Optional[str] = None
    contact_type: Optional[str] = None
    called_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DraftUpdate(BaseModel):
    body: Optional[str] = None
    subject: Optional[str] = None
    status: Optional[str] = None


class ActivityRead(BaseModel):
    id: int
    city_id: int
    action: str
    details: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
