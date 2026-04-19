from telegram import Update
from telegram.ext import ContextTypes

from services.consultation_records import (
    get_consultation_diagnosis,
    save_consultation_snapshot,
    set_consultation_diagnosis,
    set_doctor_private_notes,
)
from synmed_utils.active_chats import get_last_consultation, is_in_chat
from synmed_utils.verified_doctors import is_verified


PENDING_NOTE_KEY = "pending_consultation_note"
PENDING_SAVE_DIAGNOSIS_KEY = "pending_save_diagnosis"
SKIP_RELAY_ONCE_KEY = "skip_relay_once"


def _active_consultation_for_doctor(doctor_id: int):
    if not is_verified(doctor_id):
        return None, "Only verified doctors can add consultation notes."
    if not is_in_chat(doctor_id):
        return None, "You need an active consultation to add notes."

    consultation = get_last_consultation(doctor_id)
    if not consultation:
        return None, "Consultation record not found."
    return consultation, None


async def consultation_note_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    doctor_id = update.effective_user.id
    consultation, error_message = _active_consultation_for_doctor(doctor_id)
    if not consultation:
        await update.message.reply_text(error_message)
        return

    notes = " ".join(context.args).strip()
    diagnosis = get_consultation_diagnosis(consultation["consultation_id"])
    if notes and diagnosis:
        set_doctor_private_notes(consultation["consultation_id"], notes)
        save_consultation_snapshot(consultation["consultation_id"])
        await update.message.reply_text(
            "Consultation saved.\n"
            "Transcript, doctor note, and issued documents linked to this consultation have been archived."
        )
        return

    if not diagnosis:
        context.user_data[PENDING_SAVE_DIAGNOSIS_KEY] = {
            "consultation_id": consultation["consultation_id"],
            "note": notes,
        }
        await update.message.reply_text(
            "No diagnosis has been saved for this consultation yet.\n"
            "Please send the diagnosis in your next message so I can save the full consultation record."
        )
        return

    if not notes:
        save_consultation_snapshot(consultation["consultation_id"])
        await update.message.reply_text(
            "Consultation saved.\n"
            "Transcript and issued documents linked to this consultation have been archived."
        )
        return

    context.user_data[PENDING_NOTE_KEY] = consultation["consultation_id"]
    await update.message.reply_text(
        "Send the private doctor note in your next message and I will save it without forwarding it to the patient."
    )


async def handle_pending_consultation_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return False

    pending_diagnosis = context.user_data.get(PENDING_SAVE_DIAGNOSIS_KEY)
    if pending_diagnosis:
        diagnosis_text = update.message.text.strip()
        if not diagnosis_text:
            await update.message.reply_text("Please send the diagnosis text you want to save.")
            return True

        consultation_id = pending_diagnosis["consultation_id"]
        set_consultation_diagnosis(consultation_id, diagnosis_text)
        if pending_diagnosis.get("note"):
            set_doctor_private_notes(consultation_id, pending_diagnosis["note"])
        save_consultation_snapshot(consultation_id)
        context.user_data.pop(PENDING_SAVE_DIAGNOSIS_KEY, None)
        context.user_data[SKIP_RELAY_ONCE_KEY] = True
        await update.message.reply_text(
            "Diagnosis saved and consultation archived successfully."
        )
        return True

    consultation_id = context.user_data.get(PENDING_NOTE_KEY)
    if not consultation_id:
        return False

    note_text = update.message.text.strip()
    if not note_text:
        await update.message.reply_text("Please send the note text you want to save.")
        return True

    set_doctor_private_notes(consultation_id, note_text)
    save_consultation_snapshot(consultation_id)
    context.user_data.pop(PENDING_NOTE_KEY, None)
    context.user_data[SKIP_RELAY_ONCE_KEY] = True
    await update.message.reply_text(
        "Private consultation note saved and consultation archived."
    )
    return True
