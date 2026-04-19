from telegram import Update
from telegram.ext import ContextTypes

from services.consultation_records import get_patient_history_by_identifier
from synmed_utils.active_chats import get_last_consultation, is_in_chat
from synmed_utils.verified_doctors import is_verified


def _format_history(history: dict) -> str:
    lines = [
        f"Patient History for {history['name']}",
        f"Hospital Number: {history['patient_id']}",
        "",
        "Recent Consultations",
    ]

    if history["consultations"]:
        for item in history["consultations"]:
            lines.append(
                f"- {item['created_at']} | Doctor {item['doctor_id']} | {item['status']}"
            )
            lines.append(f"  Summary: {(item['notes'] or 'N/A')[:120]}")
    else:
        lines.append("- None")

    lines.append("")
    lines.append("Recent Diagnoses / Prescriptions")
    if history["prescriptions"]:
        for item in history["prescriptions"]:
            lines.append(
                f"- {item['created_at']} | Diagnosis: {item['diagnosis']}"
            )
    else:
        lines.append("- None")

    lines.append("")
    lines.append("Recent Investigations")
    if history["investigations"]:
        for item in history["investigations"]:
            lines.append(
                f"- {item['created_at']} | Diagnosis: {item['diagnosis']} | Tests: {item['tests_text']}"
            )
    else:
        lines.append("- None")

    return "\n".join(lines)


async def doctor_patient_history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    doctor_id = update.effective_user.id
    if not is_verified(doctor_id):
        await update.message.reply_text("Only verified doctors can review patient history.")
        return

    identifier = " ".join(context.args).strip()
    if not identifier:
        if not is_in_chat(doctor_id):
            await update.message.reply_text(
                "Usage: /patient_history <hospital_number_or_phone>\n"
                "Or use it during an active consultation to load the current patient automatically."
            )
            return

        consultation = get_last_consultation(doctor_id)
        if not consultation:
            await update.message.reply_text("Consultation record not found.")
            return

        identifier = consultation.get("patient_details", {}).get("hospital_number", "").strip()
        if not identifier:
            await update.message.reply_text("Current patient hospital number not found.")
            return

    history = get_patient_history_by_identifier(identifier)
    if not history:
        await update.message.reply_text("Patient history not found.")
        return

    await update.message.reply_text(_format_history(history))
