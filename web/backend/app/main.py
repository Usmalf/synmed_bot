import asyncio
import contextlib
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config  # noqa: F401
from database import init_db
from services import storage_service
from services.operational_errors import log_exception


app = FastAPI(title="SynMed Web API", version="0.1.0")

init_db()
storage_service.ensure_directory("generated_documents")
storage_service.ensure_directory("consultation_media")
storage_service.ensure_directory("doctor_application_files")

from .routes import admin, auth, consultations, customer_care, doctors, followups, health, patients, payments  # noqa: E402
from .services.admin_reminder_service import send_due_backup_reminders  # noqa: E402
from .services.doctor_app_service import send_due_license_expiry_reminders  # noqa: E402

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        *[
            origin.strip().rstrip("/")
            for origin in os.getenv("BACKEND_CORS_ORIGINS", "").split(",")
            if origin.strip()
        ],
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_unhandled_errors(request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        session = getattr(request.state, "session", {}) or {}
        with contextlib.suppress(Exception):
            log_exception(
                exc,
                source="web_api",
                path=str(request.url.path),
                method=request.method,
                status_code=500,
                user_role=session.get("role", ""),
                user_id=session.get("user_id", ""),
            )
        raise

app.include_router(health.router)
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(patients.router, prefix="/patients", tags=["patients"])
app.include_router(doctors.router, prefix="/doctors", tags=["doctors"])
app.include_router(consultations.router, prefix="/consultations", tags=["consultations"])
app.include_router(payments.router, prefix="/payments", tags=["payments"])
app.include_router(followups.router, prefix="/followups", tags=["followups"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(customer_care.router, prefix="/customer-care", tags=["customer-care"])
app.mount(
    "/generated-documents",
    StaticFiles(directory=str(storage_service.local_path("generated_documents"))),
    name="generated-documents",
)
app.mount(
    "/consultation-media",
    StaticFiles(directory=str(storage_service.local_path("consultation_media"))),
    name="consultation-media",
)
app.mount(
    "/doctor-application-files",
    StaticFiles(directory=str(storage_service.local_path("doctor_application_files"))),
    name="doctor-application-files",
)


@app.on_event("startup")
def on_startup():
    init_db()
    app.state.license_reminder_task = asyncio.create_task(_license_reminder_loop())
    app.state.backup_reminder_task = asyncio.create_task(_backup_reminder_loop())


@app.on_event("shutdown")
async def on_shutdown():
    tasks = [
        getattr(app.state, "license_reminder_task", None),
        getattr(app.state, "backup_reminder_task", None),
    ]
    for task in tasks:
        if not task:
            continue
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def _license_reminder_loop():
    while True:
        await asyncio.to_thread(send_due_license_expiry_reminders)
        await asyncio.sleep(60 * 60 * 24)


async def _backup_reminder_loop():
    while True:
        await asyncio.to_thread(send_due_backup_reminders)
        await asyncio.sleep(60 * 60 * 24)
