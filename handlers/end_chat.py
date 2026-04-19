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
from synmed_utils.doctor_profiles import format_doctor_intro


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


async def end_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user_id = update.effective_user.id
    restore_runtime_state()
    registry.restore_runtime_state()
    if not is_in_chat(user_id):
        await update.message.reply_text(
            "You are not currently in an active consultation."
        )
        return

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Yes, End Chat", callback_data="endchat:confirm"),
        InlineKeyboardButton("Cancel", callback_data="endchat:cancel"),
    ]])
    await update.message.reply_text(
        "Are you sure you want to end this consultation?\n"
        "This action will close the chat and prompt the patient for feedback.",
        reply_markup=keyboard,
    )


async def end_chat_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action = query.data.split(":", 1)[1]
    if action == "cancel":
        await query.edit_message_text("End chat cancelled.")
        return

    user_id = query.from_user.id
    restore_runtime_state()
    registry.restore_runtime_state()
    if not is_in_chat(user_id):
        await query.edit_message_text(
            "You are not currently in an active consultation."
        )
        return

    consultation = get_last_consultation(user_id)
    doctor_id = consultation["doctor_id"] if consultation else user_id
    patient_id = consultation["patient_id"] if consultation else None

    other_party_id = end_chat(user_id)
    if not other_party_id:
        await query.edit_message_text("Chat already ended.")
        return

    if patient_id is None:
        patient_id = other_party_id if doctor_id == user_id else user_id

    registry.remove_doctor_from_runtime(doctor_id)

    patient_details = (consultation or {}).get("patient_details") or {}
    notifications = [(doctor_id, "Consultation ended.")]
    if patient_details.get("source") != "web":
        notifications.insert(0, (patient_id, "The consultation has ended."))

    for chat_id, message in notifications:
        try:
            await context.bot.send_message(chat_id=chat_id, text=message)
        except Exception:
            pass

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("⭐ 1", callback_data="rate:1"),
        InlineKeyboardButton("⭐ 2", callback_data="rate:2"),
        InlineKeyboardButton("⭐ 3", callback_data="rate:3"),
        InlineKeyboardButton("⭐ 4", callback_data="rate:4"),
        InlineKeyboardButton("⭐ 5", callback_data="rate:5"),
    ]])
    if patient_details.get("source") != "web":
        try:
            await context.bot.send_message(
                chat_id=patient_id,
                text="Please rate your consultation:",
                reply_markup=keyboard,
            )
        except Exception:
            pass

    next_patient_id, patient_details = registry.pop_waiting_patient()
    if next_patient_id is None:
        registry.set_doctor_available(doctor_id)
        await context.bot.send_message(
            chat_id=doctor_id,
            text="You are now ONLINE and waiting for patients.",
        )
        return

    start_chat(next_patient_id, doctor_id, patient_details)
    registry.set_doctor_busy(doctor_id)

    if patient_details.get("source") != "web":
        await context.bot.send_message(
            chat_id=next_patient_id,
            text=format_doctor_intro(doctor_id),
        )
    await context.bot.send_message(
        chat_id=doctor_id,
        text=_doctor_notice_text(patient_details),
    )
