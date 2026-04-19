from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from services.consultation_records import get_latest_consultation_for_feedback
from synmed_utils.active_chats import get_last_consultation
from synmed_utils.doctor_ratings import (
    add_rating,
    get_average_rating,
    has_already_rated,
)
from synmed_utils.doctor_reviews import add_review
from synmed_utils.states import REVIEW


async def rate_doctor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        _, value = query.data.split(":")
        rating = int(value)
    except Exception:
        await query.edit_message_text("Invalid rating.")
        return ConversationHandler.END

    patient_id = query.from_user.id
    consultation = get_last_consultation(patient_id) or get_latest_consultation_for_feedback(patient_id)

    if not consultation:
        await query.edit_message_text(
            "Unable to find consultation record."
        )
        return ConversationHandler.END

    consultation_id = consultation["consultation_id"]
    doctor_id = consultation["doctor_id"]

    if has_already_rated(consultation_id):
        await query.edit_message_text(
            "You have already rated this doctor for this consultation."
        )
        return ConversationHandler.END

    add_rating(doctor_id, rating, patient_id, consultation_id)
    avg = get_average_rating(doctor_id)

    context.user_data["pending_review_doctor"] = doctor_id
    context.user_data["pending_review_rating"] = rating
    context.user_data["pending_review_consultation"] = consultation_id

    await query.edit_message_text(
        f"Thank you for your feedback!\n\n"
        f"You rated: {rating}/5\n"
        f"Doctor's average rating: {avg:.1f}/5\n\n"
        "Would you like to leave a short review?\n"
        "Reply *yes* to write one now.\n"
        "Reply *no* or *skip* to finish.",
        parse_mode="Markdown",
    )

    return REVIEW


async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    patient_id = update.effective_user.id

    doctor_id = context.user_data.get("pending_review_doctor")
    rating = context.user_data.get("pending_review_rating")
    consultation_id = context.user_data.get("pending_review_consultation")

    if not doctor_id or not rating or not consultation_id:
        await update.message.reply_text("Review session expired.")
        return ConversationHandler.END

    normalized = text.lower()

    if normalized in {"no", "skip"}:
        context.user_data.pop("pending_review_doctor", None)
        context.user_data.pop("pending_review_rating", None)
        context.user_data.pop("pending_review_consultation", None)
        await update.message.reply_text(
            "Thank you for your feedback.\n"
            "Your consultation has been completed."
        )
        return ConversationHandler.END

    if normalized == "yes":
        await update.message.reply_text(
            "Please type your short review and send it as a message."
        )
        return REVIEW

    success = add_review(doctor_id, patient_id, rating, text, consultation_id)

    if not success:
        await update.message.reply_text(
            "You have already submitted a review."
        )
        return ConversationHandler.END

    context.user_data.pop("pending_review_doctor", None)
    context.user_data.pop("pending_review_rating", None)
    context.user_data.pop("pending_review_consultation", None)
    await update.message.reply_text(
        "Thank you! Your review has been submitted."
    )

    return ConversationHandler.END
