from sqlalchemy import Boolean, Column, Integer, BigInteger, String, Text, DateTime, Date, func
from sqlalchemy.dialects.postgresql import JSONB
from database import Base


class City(Base):
    __tablename__ = "cities"

    id = Column(Integer, primary_key=True, index=True)
    city_name = Column(String(255), nullable=False, index=True)
    county = Column(String(255), index=True)
    population = Column(Integer)
    incorporated_date = Column(String(50))

    # Officials
    mayor = Column(String(255))
    mayor_pro_tem = Column(String(255))
    previous_mayor = Column(String(255))
    mayor_needs_verification = Column(Boolean, default=False)
    council_members = Column(JSONB)
    city_manager = Column(String(255))
    city_clerk = Column(String(255))
    city_attorney = Column(String(255))

    # City contact
    city_address = Column(Text)
    city_phone = Column(String(50))
    city_fax = Column(String(50))
    city_website = Column(String(500))
    city_email = Column(String(255))
    office_hours = Column(String(255))

    # Mayor direct contact (populated later)
    mayor_email = Column(String(255))
    mayor_phone = Column(String(50))
    mayor_contact_source = Column(String(255))

    # Political
    congressional_district = Column(Text)
    state_senate_district = Column(Text)
    state_assembly_district = Column(Text)
    party_affiliation = Column(String(50))

    # Insurance relevance
    fair_plan_policies = Column(Integer, default=0)
    fair_plan_exposure = Column(BigInteger, default=0)
    is_distressed_county = Column(Boolean, default=False)
    has_undermarketed_zips = Column(Boolean, default=False)
    moratorium_fires = Column(JSONB)
    moratorium_active = Column(Boolean, default=False)
    wildfire_risk_tier = Column(String(10))

    # Pipeline
    outreach_status = Column(String(50), default="no_contact_info", index=True)
    outreach_tier = Column(Integer, default=3, index=True)
    last_contacted = Column(DateTime)
    next_action = Column(Text)
    next_action_date = Column(Date)
    notes = Column(Text)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Email(Base):
    __tablename__ = "emails"

    id = Column(Integer, primary_key=True, index=True)
    city_id = Column(Integer, index=True)
    gmail_message_id = Column(String(255))
    gmail_thread_id = Column(String(255))
    direction = Column(String(10))  # inbound / outbound
    from_address = Column(String(255))
    to_address = Column(String(255))
    subject = Column(Text)
    body_preview = Column(Text)
    sent_at = Column(DateTime)
    is_draft = Column(Boolean, default=False)
    is_read = Column(Boolean, default=True, server_default='true')
    draft_type = Column(String(50))
    draft_status = Column(String(50))
    created_at = Column(DateTime, server_default=func.now())


class Draft(Base):
    __tablename__ = "drafts"

    id = Column(Integer, primary_key=True, index=True)
    city_id = Column(Integer, index=True)
    draft_type = Column(String(50), nullable=False)
    to_address = Column(String(255))
    subject = Column(Text)
    body = Column(Text)
    status = Column(String(50), default="pending_review", index=True)
    batch_id = Column(String(50), index=True)
    research_context = Column(JSONB)
    created_at = Column(DateTime, server_default=func.now())
    reviewed_at = Column(DateTime)
    sent_at = Column(DateTime)


class Settings(Base):
    __tablename__ = "settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CallLog(Base):
    __tablename__ = "call_logs"

    id = Column(Integer, primary_key=True, index=True)
    city_id = Column(Integer, index=True)
    notes = Column(Text)
    outcome = Column(String(50))  # reached, voicemail, no_answer
    contact_type = Column(String(20))  # mayor, city
    called_at = Column(DateTime, server_default=func.now())
    created_at = Column(DateTime, server_default=func.now())


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id = Column(Integer, primary_key=True, index=True)
    city_id = Column(Integer, index=True)
    action = Column(String(100))
    details = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
