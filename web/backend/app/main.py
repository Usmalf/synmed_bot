from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config  # noqa: F401
from database import init_db
from .routes import admin, auth, consultations, doctors, followups, health, patients, payments


app = FastAPI(title="SynMed Web API", version="0.1.0")

(config.ROOT_DIR / "generated_documents").mkdir(parents=True, exist_ok=True)
(config.ROOT_DIR / "consultation_media").mkdir(parents=True, exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(patients.router, prefix="/patients", tags=["patients"])
app.include_router(doctors.router, prefix="/doctors", tags=["doctors"])
app.include_router(consultations.router, prefix="/consultations", tags=["consultations"])
app.include_router(payments.router, prefix="/payments", tags=["payments"])
app.include_router(followups.router, prefix="/followups", tags=["followups"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.mount(
    "/generated-documents",
    StaticFiles(directory=str(config.ROOT_DIR / "generated_documents")),
    name="generated-documents",
)
app.mount(
    "/consultation-media",
    StaticFiles(directory=str(config.ROOT_DIR / "consultation_media")),
    name="consultation-media",
)


@app.on_event("startup")
def on_startup():
    init_db()
