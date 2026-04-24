from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from services.consent import (
    CONSENT_POLICY_TEXT,
    CONSENT_SUMMARY,
    consent_keyboard,
    has_patient_consented,
    record_patient_consent,
)
from services.interaction_state import reset_interactive_state


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_interactive_state(context.user_data)
    user_id = update.effective_user.id
    if not has_patient_consented(user_id):
        await update.message.reply_text(
            f"Welcome to *SynMed Telehealth*.\n\n{CONSENT_SUMMARY}",
            reply_markup=consent_keyboard(),
            parse_mode="Markdown",
        )
        return

    keyboard = [
        [InlineKeyboardButton("Start Consultation", callback_data="start_consult")],
        [InlineKeyboardButton("Book Appointment", callback_data="book_appointment")],
        [InlineKeyboardButton("Customer Care", callback_data="customer_care")],
    ]

    await update.message.reply_text(
        "Welcome to *SynMed Telehealth*.\n\n"
        "Choose an option below to continue.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def consent_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]

    if action == "view":
        await query.message.reply_text(
            CONSENT_POLICY_TEXT,
            reply_markup=consent_keyboard(),
        )
        return

    if action == "disagree":
        await query.edit_message_text(
            "You have declined the SynMed Telehealth consent policy.\n"
            "You will not be able to proceed with consultation until you agree."
        )
        return

    if action == "agree":
        record_patient_consent(query.from_user.id, channel="telegram")
        keyboard = [
            [InlineKeyboardButton("Start Consultation", callback_data="start_consult")],
            [InlineKeyboardButton("Book Appointment", callback_data="book_appointment")],
            [InlineKeyboardButton("Customer Care", callback_data="customer_care")],
        ]
        await query.edit_message_text(
            "Consent recorded successfully.\n\nChoose an option below to continue.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
