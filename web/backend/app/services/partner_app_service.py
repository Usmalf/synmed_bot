from datetime import datetime, timezone
from uuid import uuid4

from database import get_connection


UTC = timezone.utc
PARTNER_TYPES = {"pharmacy", "laboratory"}
PARTNER_STATUSES = {"pending", "active", "suspended"}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _partner_payload(row) -> dict:
    return {
        "partner_id": row["partner_id"],
        "name": row["name"],
        "partner_type": row["partner_type"],
        "email": row["email"] or "",
        "phone": row["phone"] or "",
        "address": row["address"] or "",
        "contact_person": row["contact_person"] or "",
        "status": row["status"],
        "notes": row["notes"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_partner_facilities() -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT partner_id, name, partner_type, email, phone, address,
                   contact_person, status, notes, created_at, updated_at
            FROM partner_facilities
            ORDER BY datetime(created_at) DESC
            """
        )
        rows = cursor.fetchall()

    partners = [_partner_payload(row) for row in rows]
    return {
        "partners": partners,
        "summary": {
            "total": len(partners),
            "active": sum(1 for partner in partners if partner["status"] == "active"),
            "pending": sum(1 for partner in partners if partner["status"] == "pending"),
            "suspended": sum(1 for partner in partners if partner["status"] == "suspended"),
        },
    }


def create_partner_facility(payload: dict) -> dict:
    name = (payload.get("name") or "").strip()
    partner_type = (payload.get("partner_type") or "").strip().lower()
    status = (payload.get("status") or "pending").strip().lower()

    if not name:
        return {"created": False, "message": "Partner name is required.", "partner": None}
    if partner_type not in PARTNER_TYPES:
        return {"created": False, "message": "Partner type must be pharmacy or laboratory.", "partner": None}
    if status not in PARTNER_STATUSES:
        return {"created": False, "message": "Partner status is not supported.", "partner": None}

    partner_id = f"pt-{uuid4().hex[:12]}"
    now = _now_iso()
    values = {
        "partner_id": partner_id,
        "name": name,
        "partner_type": partner_type,
        "email": (payload.get("email") or "").strip().lower(),
        "phone": (payload.get("phone") or "").strip(),
        "address": (payload.get("address") or "").strip(),
        "contact_person": (payload.get("contact_person") or "").strip(),
        "status": status,
        "notes": (payload.get("notes") or "").strip(),
        "created_at": now,
        "updated_at": now,
    }

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO partner_facilities (
                partner_id, name, partner_type, email, phone, address,
                contact_person, status, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["partner_id"],
                values["name"],
                values["partner_type"],
                values["email"],
                values["phone"],
                values["address"],
                values["contact_person"],
                values["status"],
                values["notes"],
                values["created_at"],
                values["updated_at"],
            ),
        )
        conn.commit()

    return {"created": True, "message": "Partner facility created.", "partner": values}


def update_partner_status(partner_id: str, status: str) -> dict:
    normalized_status = (status or "").strip().lower()
    if normalized_status not in PARTNER_STATUSES:
        return {"updated": False, "message": "Partner status is not supported.", "partner": None}

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE partner_facilities
            SET status = ?, updated_at = ?
            WHERE partner_id = ?
            """,
            (normalized_status, _now_iso(), partner_id),
        )
        conn.commit()
        if cursor.rowcount < 1:
            return {"updated": False, "message": "Partner facility could not be found.", "partner": None}
        cursor.execute(
            """
            SELECT partner_id, name, partner_type, email, phone, address,
                   contact_person, status, notes, created_at, updated_at
            FROM partner_facilities
            WHERE partner_id = ?
            """,
            (partner_id,),
        )
        partner = cursor.fetchone()

    return {"updated": True, "message": "Partner status updated.", "partner": _partner_payload(partner)}
