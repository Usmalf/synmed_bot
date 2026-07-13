from datetime import datetime, timezone
from uuid import uuid4

import synmed_utils.doctor_registry as registry
from database import get_connection
from services.consultation_records import log_consultation_message
from synmed_utils.active_chats import get_last_consultation, transfer_chat_to_doctor
from synmed_utils.doctor_profiles import doctor_profiles


UTC = timezone.utc


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _doctor_name(doctor_id: int | str) -> str:
    try:
        profile = doctor_profiles.get(int(doctor_id), {}) or {}
    except (TypeError, ValueError):
        profile = {}
    return profile.get("name") or f"Doctor {doctor_id}"


def list_transfer_eligible_doctors(current_doctor_id: int | str) -> list[dict]:
    current = str(current_doctor_id)
    doctors = []
    for doctor_id in sorted(registry.available_doctors_by_channel.get("web", set())):
        if str(doctor_id) == current:
            continue
        profile = doctor_profiles.get(int(doctor_id), {}) or {}
        if not profile.get("verified"):
            continue
        doctors.append(
            {
                "doctor_id": int(doctor_id),
                "name": profile.get("name") or f"Doctor {doctor_id}",
                "specialty": profile.get("specialty") or "N/A",
            }
        )
    return doctors


def list_doctor_transfer_requests(doctor_id: int | str) -> dict:
    doctor_id = str(doctor_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT transfer_id, consultation_id, patient_id, from_doctor_id, to_doctor_id,
                   handover_note, status, requested_at, responded_at
            FROM consultation_transfer_requests
            WHERE status = 'pending'
              AND (from_doctor_id = ? OR to_doctor_id = ?)
            ORDER BY datetime(requested_at) DESC, id DESC
            """,
            (doctor_id, doctor_id),
        )
        rows = [dict(row) for row in cursor.fetchall()]

    incoming = []
    outgoing = []
    for row in rows:
        row["from_doctor_name"] = _doctor_name(row["from_doctor_id"])
        row["to_doctor_name"] = _doctor_name(row["to_doctor_id"])
        if str(row["to_doctor_id"]) == doctor_id:
            incoming.append(row)
        else:
            outgoing.append(row)
    return {"incoming": incoming, "outgoing": outgoing}


def create_transfer_request(from_doctor_id: int | str, to_doctor_id: int | str, handover_note: str = "") -> dict:
    consultation = get_last_consultation(from_doctor_id)
    if not consultation:
        return {"created": False, "message": "No active consultation to transfer."}
    if str(from_doctor_id) == str(to_doctor_id):
        return {"created": False, "message": "Select another doctor for transfer."}
    if int(to_doctor_id) not in registry.available_doctors_by_channel.get("web", set()):
        return {"created": False, "message": "Selected doctor is not online and available."}

    transfer_id = f"transfer-{uuid4().hex[:14]}"
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE consultation_transfer_requests
            SET status = 'cancelled', responded_at = ?
            WHERE consultation_id = ? AND from_doctor_id = ? AND status = 'pending'
            """,
            (_now_iso(), consultation["consultation_id"], str(from_doctor_id)),
        )
        cursor.execute(
            """
            INSERT INTO consultation_transfer_requests (
                transfer_id, consultation_id, patient_id, from_doctor_id, to_doctor_id,
                handover_note, status, requested_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                transfer_id,
                consultation["consultation_id"],
                str(consultation["patient_id"]),
                str(from_doctor_id),
                str(to_doctor_id),
                handover_note.strip(),
                _now_iso(),
            ),
        )
        conn.commit()

    log_consultation_message(
        consultation["consultation_id"],
        sender_id=int(from_doctor_id),
        sender_role="system",
        message_text=f"Transfer requested to {_doctor_name(to_doctor_id)}.",
    )
    return {"created": True, "message": "Transfer request sent.", "transfer_id": transfer_id}


def respond_to_transfer_request(doctor_id: int | str, transfer_id: str, action: str) -> dict:
    normalized = (action or "").strip().lower()
    if normalized not in {"accept", "decline"}:
        return {"updated": False, "message": "Unsupported transfer response."}

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT transfer_id, consultation_id, patient_id, from_doctor_id, to_doctor_id,
                   handover_note, status
            FROM consultation_transfer_requests
            WHERE transfer_id = ?
            """,
            (transfer_id,),
        )
        request = cursor.fetchone()
        if not request or request["status"] != "pending" or str(request["to_doctor_id"]) != str(doctor_id):
            return {"updated": False, "message": "Transfer request is no longer available."}

        if normalized == "decline":
            cursor.execute(
                """
                UPDATE consultation_transfer_requests
                SET status = 'declined', responded_at = ?
                WHERE transfer_id = ?
                """,
                (_now_iso(), transfer_id),
            )
            conn.commit()
            return {"updated": True, "message": "Transfer request declined."}

    consultation = transfer_chat_to_doctor(
        int(request["from_doctor_id"]),
        int(request["to_doctor_id"]),
        request["handover_note"] or "",
    )
    if not consultation:
        return {"updated": False, "message": "The consultation is no longer active."}

    registry.set_doctor_available(int(request["from_doctor_id"]), channel="web")
    registry.set_doctor_busy(int(request["to_doctor_id"]), channel="web")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE consultation_transfer_requests
            SET status = 'accepted', responded_at = ?
            WHERE transfer_id = ?
            """,
            (_now_iso(), transfer_id),
        )
        conn.commit()

    log_consultation_message(
        consultation["consultation_id"],
        sender_id=int(request["to_doctor_id"]),
        sender_role="system",
        message_text=f"Consultation transferred from {_doctor_name(request['from_doctor_id'])} to {_doctor_name(request['to_doctor_id'])}.",
    )
    return {
        "updated": True,
        "message": "Transfer accepted. Consultation moved to your workspace.",
        "consultation_id": consultation["consultation_id"],
    }
