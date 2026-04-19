from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Start Consultation", callback_data="start_consult")],
        [InlineKeyboardButton("Book Appointment", callback_data="book_appointment")],
        [InlineKeyboardButton("Customer Care", callback_data="customer_care")],
    ]

    await update.message.reply_text(
        "Welcome to *SynMed Telehealth*.\n\n"
        "By continuing, you consent to remote medical consultation.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
