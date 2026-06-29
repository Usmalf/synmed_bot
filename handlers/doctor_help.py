from telegram import Update
from telegram.ext import ContextTypes


async def doctor_help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    text = (
        "Doctor Commands\n\n"
        "/request_doctor - Apply for doctor approval\n"
        "/doctor_on - Go online for consultations\n"
        "/doctor_off - Go offline\n"
        "/end_chat - End the active consultation\n"
        "/save_note <private note> - Save a private consultation note\n"
        "/patient_history - Review the current patient's history\n"
        "/patient_history <hospital number or phone> - Review a specific patient's history\n"
        "/followup <YYYY-MM-DD HH:MM> | <notes> - Schedule a follow-up appointment\n"
        "/prescription - Create a prescription PDF\n"
        "/investigation - Create an investigation request PDF\n"
        "/cancel_doc - Cancel the current document draft\n"
        "/doctor_help - Show this help message"
    )
    await update.message.reply_text(text)
