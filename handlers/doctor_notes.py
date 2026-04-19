from telegram import Update
from telegram.ext import ContextTypes

from services.consultation_records import set_doctor_private_notes
from synmed_utils.active_chats import get_last_consultation, is_in_chat
from synmed_utils.verified_doctors import is_verified


async def consultation_note_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    doctor_id = update.effective_user.id
    if not is_verified(doctor_id):
        await update.message.reply_text("Only verified doctors can add consultation notes.")
        return

    if not is_in_chat(doctor_id):
        await update.message.reply_text("You need an active consultation to add notes.")
        return

    consultation = get_last_consultation(doctor_id)
    if not consultation:
        await update.message.reply_text("Consultation record not found.")
        return

    notes = " ".join(context.args).strip()
    if not notes:
        await update.message.reply_text(
            "Usage: /save_note <private doctor note>"
        )
        return

    set_doctor_private_notes(consultation["consultation_id"], notes)
    await update.message.reply_text("Private consultation note saved.")
