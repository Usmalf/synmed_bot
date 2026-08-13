import os
import asyncio
from datetime import datetime, timezone

import httpx

from synmed_utils.admin import get_admins


UTC = timezone.utc
MAX_SYMPTOM_PREVIEW = 700


def _clean_text(value: object, fallback: str = "N/A") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def consultation_queue_alert_text(patient_details: dict, *, channel: str = "web") -> str:
    symptoms = _clean_text(patient_details.get("history"), "No symptom summary provided.")
    if len(symptoms) > MAX_SYMPTOM_PREVIEW:
        symptoms = f"{symptoms[:MAX_SYMPTOM_PREVIEW].rstrip()}..."

    urgency = "Emergency flagged" if patient_details.get("emergency_flag") else "Routine queue"
    submitted_at = _clean_text(patient_details.get("submitted_at"), datetime.now(UTC).isoformat())
    source = _clean_text(channel or patient_details.get("channel") or patient_details.get("source"), "web").title()

    return (
        "New patient awaiting consultation\n\n"
        f"Source: {source}\n"
        f"Priority: {urgency}\n"
        f"Queued: {submitted_at}\n\n"
        f"Patient: {_clean_text(patient_details.get('name'))}\n"
        f"Hospital No: {_clean_text(patient_details.get('hospital_number'))}\n"
        f"Age/Gender: {_clean_text(patient_details.get('age'))} / {_clean_text(patient_details.get('gender'))}\n"
        f"Phone: {_clean_text(patient_details.get('phone'))}\n\n"
        f"Symptoms:\n{symptoms}\n\n"
        "Open the doctor dashboard and click Connect when ready."
    )


async def _send_telegram_text(chat_id: int, text: str) -> bool:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        return False

    async with httpx.AsyncClient(timeout=12) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )
    response.raise_for_status()
    return True


async def notify_admins_patient_queued(patient_details: dict, *, channel: str = "web", bot=None) -> int:
    text = consultation_queue_alert_text(patient_details, channel=channel)
    delivered = 0

    for admin_id in get_admins():
        try:
            if bot is not None:
                await bot.send_message(chat_id=admin_id, text=text)
                sent = True
            else:
                sent = await _send_telegram_text(admin_id, text)
            if sent:
                delivered += 1
        except Exception:
            continue

    return delivered


def dispatch_admins_patient_queued(patient_details: dict, *, channel: str = "web", bot=None) -> None:
    try:
        asyncio.get_running_loop().create_task(
            notify_admins_patient_queued(patient_details, channel=channel, bot=bot)
        )
    except RuntimeError:
        return
