from telegram import Update
from telegram.ext import ContextTypes

from services.consultation_records import get_patient_history


async def patient_history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    history = get_patient_history(update.effective_user.id)
    if not history:
        await update.message.reply_text(
            "No patient history found for this Telegram account."
        )
        return

    lines = [
        f"Patient History for {history['name']}",
        f"Hospital Number: {history['patient_id']}",
        "",
        "Recent Consultations",
    ]

    if history["consultations"]:
        for item in history["consultations"]:
            lines.append(
                f"- {item['consultation_id'][:8]} | Doctor {item['doctor_id']} | {item['status']} | {item['created_at']}"
            )
    else:
        lines.append("- None")

    lines.append("")
    lines.append(f"Recent Prescriptions: {len(history['prescriptions'])}")
    lines.append(f"Recent Investigations: {len(history['investigations'])}")
    await update.message.reply_text("\n".join(lines))
