from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import synmed_utils.doctor_registry as registry
from synmed_utils.active_chats import (
    end_chat,
    get_last_consultation,
    is_in_chat,
    restore_runtime_state,
    start_chat,
)
from synmed_utils.doctor_profiles import doctor_profiles, verified_badge
from synmed_utils.doctor_ratings import get_average_rating, get_total_ratings
from synmed_utils.verified_doctors import is_verified


def _doctor_notice_text(patient_details: dict) -> str:
    source_note = (
        "\nThis patient is consulting via SynMed Web. Reply here in Telegram and the patient will see your messages in the website consultation room."
        if patient_details.get("source") == "web"
        else ""
    )
    return (
        "New Patient Connected\n\n"
        f"Hospital Number: {patient_details.get('hospital_number', 'N/A')}\n"
        f"Name: {patient_details.get('name', 'N/A')}\n"
        f"Age: {patient_details.get('age', 'N/A')}\n"
        f"Gender: {patient_details.get('gender', 'N/A')}\n"
        f"Phone: {patient_details.get('phone', 'N/A')}\n"
        f"Address: {patient_details.get('address', 'N/A')}\n"
        f"Allergy: {patient_details.get('allergy', 'None recorded')}\n\n"
        "Medical History / Symptoms:\n"
        f"{patient_details.get('history', 'N/A')}\n\n"
        f"You may begin consultation.{source_note}"
    )


async def doctor_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    doctor_id = update.effective_user.id
    restore_runtime_state()
    registry.restore_runtime_state()

    if update.effective_chat.type != "private":
        await update.message.reply_text(
            "Please use this command in a private chat."
        )
        return

    if not is_verified(doctor_id):
        await update.message.reply_text(
            "You are not a verified doctor on SynMed.\n\n"
            "Please submit your credentials using:\n"
            "/request_doctor"
        )
        return

    if is_in_chat(doctor_id):
        await update.message.reply_text(
            "You are already in an active consultation.\n"
            "Use /end_chat to finish it."
        )
        return

    if doctor_id in registry.available_doctors:
        await update.message.reply_text(
            "You are already ONLINE and waiting for patients."
        )
        return

    profile = doctor_profiles.get(doctor_id, {})
    doctor_name = profile.get("name", "Doctor")
    specialty = profile.get("specialty", "N/A")
    experience = profile.get("experience", "N/A")

    patient_id, patient_details = registry.pop_waiting_patient()
    if patient_id is None:
        registry.set_doctor_available(doctor_id)
        await update.message.reply_text(
            "You are ONLINE and waiting for patients."
        )
        return

    start_chat(patient_id, doctor_id, patient_details)
    registry.set_doctor_busy(doctor_id)

    avg_rating = get_average_rating(doctor_id)
    total_reviews = get_total_ratings(doctor_id)
    rating_text = (
        f"{avg_rating:.1f} star ({total_reviews} reviews)"
        if total_reviews > 0
        else "No ratings yet"
    )

    if patient_details.get("source") != "web":
        await context.bot.send_message(
            chat_id=patient_id,
            text=(
                "You are now connected to:\n\n"
                f"Dr. {doctor_name}{verified_badge(doctor_id)}\n"
                f"- Specialty: {specialty}\n"
                f"- Experience: {experience} years\n"
                f"- Rating: {rating_text}\n\n"
                "You may begin chatting."
            ),
        )

    await context.bot.send_message(
        chat_id=doctor_id,
        text=_doctor_notice_text(patient_details),
    )


async def doctor_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    doctor_id = update.effective_user.id
    restore_runtime_state()
    registry.restore_runtime_state()
    registry.remove_doctor_from_runtime(doctor_id)
    consultation = get_last_consultation(doctor_id)
    patient_details = (consultation or {}).get("patient_details") or {}

    partner_id = end_chat(doctor_id)
    if not partner_id:
        await update.message.reply_text("You are now OFFLINE.")
        return

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("⭐ 1", callback_data="rate:1"),
        InlineKeyboardButton("⭐ 2", callback_data="rate:2"),
        InlineKeyboardButton("⭐ 3", callback_data="rate:3"),
        InlineKeyboardButton("⭐ 4", callback_data="rate:4"),
        InlineKeyboardButton("⭐ 5", callback_data="rate:5"),
    ]])

    if patient_details.get("source") != "web":
        await context.bot.send_message(
            chat_id=partner_id,
            text="Please rate your consultation:",
            reply_markup=keyboard,
        )
    await update.message.reply_text(
        "Consultation ended. You are now OFFLINE."
    )
