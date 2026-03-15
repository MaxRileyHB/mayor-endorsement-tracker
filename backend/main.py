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
        _conn.commit()
except Exception as _e:
    print(f"Migration warning (non-fatal): {_e}")

from routers import cities, drafts, auth, emails

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


@app.get("/health")
def health():
    return {"status": "ok"}
