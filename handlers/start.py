from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from services.consent import build_policy_text, has_user_agreed, record_user_consent


def build_home_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("Start Consultation", callback_data="start_consult")],
        [InlineKeyboardButton("Book Appointment", callback_data="book_appointment")],
        [InlineKeyboardButton("Customer Care", callback_data="customer_care")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_consent_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("View Full Policy", callback_data="consent:view")],
        [
            InlineKeyboardButton("I Agree", callback_data="consent:agree"),
            InlineKeyboardButton("I Disagree", callback_data="consent:decline"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def _send_main_menu(target_message):
    await target_message.reply_text(
        "Welcome to *SynMed Telehealth*.\n\nChoose what you would like to do next.",
        reply_markup=build_home_keyboard(),
        parse_mode="Markdown",
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user_id = update.effective_user.id
    if has_user_agreed(user_id):
        await _send_main_menu(update.message)
        return

    await update.message.reply_text(
        build_policy_text(full=False),
        reply_markup=build_consent_keyboard(),
        parse_mode="Markdown",
    )


async def handle_consent_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    await query.answer()
    action = query.data.split(":", 1)[1]
    user_id = query.from_user.id

    if action == "view":
        await query.message.reply_text(
            build_policy_text(full=True),
            reply_markup=build_consent_keyboard(),
            parse_mode="Markdown",
        )
        return

    if action == "agree":
        record_user_consent(user_id, agreed=True)
        await query.edit_message_text(
            "Thank you. Your data protection and telemedicine consent has been recorded.",
            parse_mode="Markdown",
        )
        await _send_main_menu(query.message)
        return

    if action == "decline":
        record_user_consent(user_id, agreed=False)
        await query.edit_message_text(
            "You declined the consent notice. SynMed cannot continue with consultation until you agree to the policy.",
            parse_mode="Markdown",
        )
