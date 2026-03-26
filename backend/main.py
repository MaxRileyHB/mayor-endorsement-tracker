from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from database import engine
import models

models.Base.metadata.create_all(bind=engine)

# Idempotent migrations for columns added after initial deploy
try:
    with engine.connect() as _conn:
        _conn.execute(text(
            "ALTER TABLE emails ADD COLUMN IF NOT EXISTS is_read BOOLEAN NOT NULL DEFAULT TRUE"
        ))
        _conn.execute(text("ALTER TABLE emails ALTER COLUMN from_address TYPE TEXT"))
        _conn.execute(text("ALTER TABLE emails ALTER COLUMN to_address TYPE TEXT"))
        # Mayor expanded contact fields
        _conn.execute(text("ALTER TABLE cities ADD COLUMN IF NOT EXISTS mayor_work_email VARCHAR(255)"))
        _conn.execute(text("ALTER TABLE cities ADD COLUMN IF NOT EXISTS mayor_work_email_source VARCHAR(500)"))
        _conn.execute(text("ALTER TABLE cities ADD COLUMN IF NOT EXISTS mayor_work_phone VARCHAR(50)"))
        _conn.execute(text("ALTER TABLE cities ADD COLUMN IF NOT EXISTS mayor_work_phone_source VARCHAR(500)"))
        _conn.execute(text("ALTER TABLE cities ADD COLUMN IF NOT EXISTS mayor_personal_email VARCHAR(255)"))
        _conn.execute(text("ALTER TABLE cities ADD COLUMN IF NOT EXISTS mayor_personal_email_source VARCHAR(500)"))
        _conn.execute(text("ALTER TABLE cities ADD COLUMN IF NOT EXISTS mayor_personal_phone VARCHAR(50)"))
        _conn.execute(text("ALTER TABLE cities ADD COLUMN IF NOT EXISTS mayor_personal_phone_source VARCHAR(500)"))
        _conn.execute(text("ALTER TABLE cities ADD COLUMN IF NOT EXISTS mayor_instagram VARCHAR(255)"))
        _conn.execute(text("ALTER TABLE cities ADD COLUMN IF NOT EXISTS mayor_instagram_source VARCHAR(500)"))
        _conn.execute(text("ALTER TABLE cities ADD COLUMN IF NOT EXISTS mayor_facebook VARCHAR(500)"))
        _conn.execute(text("ALTER TABLE cities ADD COLUMN IF NOT EXISTS mayor_facebook_source VARCHAR(500)"))
        _conn.execute(text("ALTER TABLE cities ADD COLUMN IF NOT EXISTS mayor_other_social_platform VARCHAR(100)"))
        _conn.execute(text("ALTER TABLE cities ADD COLUMN IF NOT EXISTS mayor_other_social_handle VARCHAR(255)"))
        _conn.execute(text("ALTER TABLE cities ADD COLUMN IF NOT EXISTS mayor_other_social_source VARCHAR(500)"))
        _conn.execute(text("ALTER TABLE cities ADD COLUMN IF NOT EXISTS contact_scrape_status VARCHAR(50) DEFAULT 'not_scraped'"))
        _conn.execute(text("ALTER TABLE cities ADD COLUMN IF NOT EXISTS contact_scrape_date TIMESTAMP"))
        _conn.execute(text("ALTER TABLE cities ADD COLUMN IF NOT EXISTS contact_scrape_log TEXT"))
        _conn.execute(text("ALTER TABLE cities ADD COLUMN IF NOT EXISTS city_blurb TEXT"))
        _conn.execute(text("ALTER TABLE cities ADD COLUMN IF NOT EXISTS mayor_last_name VARCHAR(255)"))
        # Bounce / invalid email tracking
        _conn.execute(text("ALTER TABLE cities ADD COLUMN IF NOT EXISTS mayor_work_email_invalid BOOLEAN NOT NULL DEFAULT FALSE"))
        _conn.execute(text("ALTER TABLE cities ADD COLUMN IF NOT EXISTS mayor_personal_email_invalid BOOLEAN NOT NULL DEFAULT FALSE"))
        _conn.execute(text("ALTER TABLE emails ADD COLUMN IF NOT EXISTS is_bounce BOOLEAN NOT NULL DEFAULT FALSE"))
        # Recompute outreach_tier using the algorithmic email tier system
        _conn.execute(text("""
            UPDATE cities SET outreach_tier =
              CASE
                WHEN population >= 100000 THEN 1
                WHEN population BETWEEN 30000 AND 99999 THEN 2
                WHEN fair_plan_policies >= 1000 THEN 2
                WHEN moratorium_active = true THEN 2
                WHEN is_distressed_county = true AND population >= 15000 THEN 2
                WHEN has_undermarketed_zips = true THEN 2
                WHEN wildfire_risk_tier = 'high' THEN 2
                ELSE 3
              END
        """))
        # Migrate legacy mayor_email / mayor_phone into the new work fields (only where new fields are blank)
        _conn.execute(text("""
            UPDATE cities
            SET mayor_work_email = mayor_email
            WHERE mayor_email IS NOT NULL AND mayor_email != ''
              AND (mayor_work_email IS NULL OR mayor_work_email = '')
        """))
        _conn.execute(text("""
            UPDATE cities
            SET mayor_work_phone = mayor_phone
            WHERE mayor_phone IS NOT NULL AND mayor_phone != ''
              AND (mayor_work_phone IS NULL OR mayor_work_phone = '')
        """))
        _conn.execute(text(
            "CREATE TABLE IF NOT EXISTS mail_merge_templates ("
            "  id SERIAL PRIMARY KEY,"
            "  name VARCHAR(255) NOT NULL,"
            "  subject_template TEXT NOT NULL,"
            "  body_template TEXT NOT NULL,"
            "  created_at TIMESTAMP DEFAULT NOW(),"
            "  updated_at TIMESTAMP DEFAULT NOW()"
            ")"
        ))
        _conn.execute(text(
            "CREATE TABLE IF NOT EXISTS mail_merge_jobs ("
            "  id VARCHAR(50) PRIMARY KEY,"
            "  template_id INTEGER,"
            "  status VARCHAR(20) DEFAULT 'running',"
            "  total INTEGER DEFAULT 0,"
            "  sent INTEGER DEFAULT 0,"
            "  skipped INTEGER DEFAULT 0,"
            "  failed INTEGER DEFAULT 0,"
            "  current_city VARCHAR(255),"
            "  stagger_seconds INTEGER DEFAULT 30,"
            "  city_plan JSONB,"
            "  skipped_cities JSONB,"
            "  created_at TIMESTAMP DEFAULT NOW(),"
            "  completed_at TIMESTAMP"
            ")"
        ))
        _conn.commit()
except Exception as _e:
    print(f"Migration warning (non-fatal): {_e}")

from routers import cities, drafts, auth, emails
from routers import mail_merge

app = FastAPI(title="Mayor CRM API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cities.router)
app.include_router(drafts.router)
app.include_router(auth.router)
app.include_router(emails.router)
app.include_router(mail_merge.router)


@app.get("/health")
def health():
    return {"status": "ok"}
