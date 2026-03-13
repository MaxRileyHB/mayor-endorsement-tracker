from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine
import models

models.Base.metadata.create_all(bind=engine)

from routers import cities, drafts

app = FastAPI(title="Mayor CRM API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cities.router)
app.include_router(drafts.router)


@app.get("/health")
def health():
    return {"status": "ok"}
