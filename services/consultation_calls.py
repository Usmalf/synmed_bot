import json
from threading import RLock
from datetime import datetime, timezone

from database import get_connection

UTC = timezone.utc
_CALL_STATE_LOCK = RLock()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _default_state(consultation_id: str) -> dict:
    return {
        "consultation_id": consultation_id,
        "status": "idle",
        "call_type": None,
        "initiated_by": None,
        "offer_sdp": None,
        "answer_sdp": None,
        "patient_candidates": [],
        "doctor_candidates": [],
        "started_at": None,
        "connected_at": None,
        "updated_at": _now_iso(),
    }


def get_consultation_call_state(consultation_id: str) -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT state_json
                FROM consultation_calls_runtime
                WHERE consultation_id = ?
                """,
                (consultation_id,),
            )
            row = cursor.fetchone()
        except Exception:
            row = None

    if not row or not row["state_json"]:
        return _default_state(consultation_id)

    try:
        parsed = json.loads(row["state_json"])
    except json.JSONDecodeError:
        parsed = {}

    merged = {
        **_default_state(consultation_id),
        **parsed,
        "consultation_id": consultation_id,
    }
    merged["patient_candidates"] = merged.get("patient_candidates") or []
    merged["doctor_candidates"] = merged.get("doctor_candidates") or []
    return merged


def save_consultation_call_state(consultation_id: str, state: dict) -> dict:
    normalized = {
        **_default_state(consultation_id),
        **(state or {}),
        "consultation_id": consultation_id,
        "updated_at": _now_iso(),
    }
    if normalized["status"] in {"ringing", "connecting", "active"} and not normalized.get("started_at"):
        normalized["started_at"] = _now_iso()
    if normalized["status"] == "active" and not normalized.get("connected_at"):
        normalized["connected_at"] = _now_iso()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO consultation_calls_runtime (consultation_id, state_json)
            VALUES (?, ?)
            ON CONFLICT(consultation_id) DO UPDATE SET
                state_json = excluded.state_json
            """,
            (consultation_id, json.dumps(normalized)),
        )
        conn.commit()
    return normalized


def update_consultation_call_state(consultation_id: str, transform) -> dict:
    with _CALL_STATE_LOCK:
        current = get_consultation_call_state(consultation_id)
        next_state = transform(current)
        return save_consultation_call_state(consultation_id, next_state)


def clear_consultation_call_state(consultation_id: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM consultation_calls_runtime WHERE consultation_id = ?",
            (consultation_id,),
        )
        conn.commit()
