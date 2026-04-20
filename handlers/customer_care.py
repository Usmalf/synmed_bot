from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from handlers.admin_patient import (
    ADMIN_PENDING_ACTION_KEY,
    CONSULTATION_MENU_ACTION,
    PATIENT_DOCS_MENU_ACTION,
    PATIENT_EDIT_DATA_KEY,
    PATIENT_EDIT_IDENTIFIER_ACTION,
    PATIENT_LOOKUP_ACTION,
    PATIENT_SEARCH_ACTION,
)
from synmed_utils.support_registry import (
    available_support_agents,
    is_in_support_chat,
    is_support_approved,
    queue_support_user,
    start_support_chat,
    support_profiles,
)


FAQ_RESPONSES = {
    "hospital_number": (
        "Hospital Number Help\n\n"
        "Your hospital number is issued after successful registration and payment.\n"
        "If you already registered, use your hospital number or phone number to return for consultation."
    ),
    "payment": (
        "Payment Help\n\n"
        "New patients pay NGN 5,000 total.\n"
        "This covers NGN 2,000 for registration and NGN 3,000 for consultation.\n"
        "Returning patients pay NGN 3,000 per consultation.\n"
        "After payment, return to Telegram and tap `I Have Paid` to continue."
    ),
    "documents": (
        "Prescription / Investigation Help\n\n"
        "After your doctor issues a prescription or investigation request, it is sent to you as a downloadable PDF inside Telegram."
    ),
    "doctor_status": (
        "Doctor Approval Help\n\n"
        "Doctors must submit credentials and wait for admin approval before they can go online and receive consultations."
    ),
}


def _customer_care_menu() -> InlineKeyboardMarkup:
    return _customer_care_menu_for_support(False)


def _customer_care_menu_for_support(is_support_user: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Hospital Number Help", callback_data="customerfaq:hospital_number")],
        [InlineKeyboardButton("Payment Help", callback_data="customerfaq:payment")],
        [InlineKeyboardButton("Prescription / Investigation Help", callback_data="customerfaq:documents")],
        [InlineKeyboardButton("Doctor Approval Help", callback_data="customerfaq:doctor_status")],
        [InlineKeyboardButton("Talk to Human Support", callback_data="customerhuman:connect")],
    ]
    if is_support_user:
        rows.extend(
            [
                [
                    InlineKeyboardButton("Patient Record", callback_data="customersupport:patient_record"),
                    InlineKeyboardButton("Edit Patient", callback_data="customersupport:edit_patient"),
                ],
                [
                    InlineKeyboardButton("Consultation", callback_data="customersupport:consultation"),
                    InlineKeyboardButton("Patient Docs", callback_data="customersupport:patient_docs"),
                ],
                [
                    InlineKeyboardButton("Search Records", callback_data="customersupport:search_records"),
                ],
            ]
        )
    return InlineKeyboardMarkup(rows)


async def customer_care_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        "SynMed Customer Care\n\n"
        "Choose a help topic below, or connect to a live support agent."
    )
    if user and is_support_approved(user.id):
        text += (
            "\n\nSupport tools:\n"
            "/patient_record <hospital_number_or_phone>\n"
            "/edit_patient <hospital_number_or_phone> | <field> | <value>\n"
            "/export_consultation <consultation_id_or_hospital_number>\n"
            "/consultation_bundle <consultation_id_or_hospital_number>\n"
            "/resend_docs <consultation_id_or_hospital_number> [patient]"
        )
    menu = _customer_care_menu_for_support(bool(user and is_support_approved(user.id)))

    query = getattr(update, "callback_query", None)
    if query:
        await query.answer()
        await query.message.reply_text(text, reply_markup=menu)
        return

    message = getattr(update, "message", None)
    if message:
        await message.reply_text(text, reply_markup=menu)


async def customer_care_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, payload = query.data.split(":", 1)
    if action == "customerfaq":
        answer = FAQ_RESPONSES.get(payload, "Support information unavailable right now.")
        await query.edit_message_text(
            answer,
            reply_markup=_customer_care_menu_for_support(is_support_approved(query.from_user.id)),
        )
        return

    if action == "customersupport":
        if not is_support_approved(query.from_user.id):
            await query.edit_message_text("Approved support agents only.")
            return

        if payload == "patient_record":
            context.user_data[ADMIN_PENDING_ACTION_KEY] = PATIENT_LOOKUP_ACTION
            await query.edit_message_text("Enter the patient's hospital number or phone number.")
            return

        if payload == "edit_patient":
            context.user_data[ADMIN_PENDING_ACTION_KEY] = PATIENT_EDIT_IDENTIFIER_ACTION
            context.user_data.pop(PATIENT_EDIT_DATA_KEY, None)
            await query.edit_message_text(
                "Enter the patient's hospital number or phone number to edit the record."
            )
            return

        if payload == "consultation":
            context.user_data[ADMIN_PENDING_ACTION_KEY] = CONSULTATION_MENU_ACTION
            await query.edit_message_text(
                "Enter the consultation ID or patient hospital number."
            )
            return

        if payload == "patient_docs":
            context.user_data[ADMIN_PENDING_ACTION_KEY] = PATIENT_DOCS_MENU_ACTION
            await query.edit_message_text(
                "Enter the consultation ID or patient hospital number to open document options."
            )
            return

        if payload == "search_records":
            context.user_data[ADMIN_PENDING_ACTION_KEY] = PATIENT_SEARCH_ACTION
            await query.edit_message_text(
                "Enter the patient name, hospital number, or phone number to search."
            )
            return

    user_id = query.from_user.id
    if is_in_support_chat(user_id):
        await query.edit_message_text("You are already connected to a support agent.")
        return

    if available_support_agents:
        agent_id = available_support_agents.pop()
        start_support_chat(user_id, agent_id)
        profile = support_profiles.get(agent_id, {})
        agent_name = profile.get("name", "Support Agent")
        await context.bot.send_message(
            chat_id=agent_id,
            text=f"You are now connected to customer {user_id}.",
        )
        await query.edit_message_text(
            "You are now connected to SynMed Customer Care.\n\n"
            f"Agent: {agent_name}\n"
            "You may begin chatting."
        )
        return

    queue_support_user(user_id)
    await query.edit_message_text(
        "All human support agents are currently busy.\n"
        "You have been added to the support queue and will be connected shortly."
    )
