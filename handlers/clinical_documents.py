from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from services.clinical_documents import (
    create_investigation_document,
    create_medical_report_document,
    create_prescription_document,
    create_referral_document,
)
from services.interaction_state import reset_interactive_state
from services.consultation_records import log_consultation_event
from services.consultation_records import get_consultation_diagnosis, set_consultation_diagnosis
from synmed_utils.active_chats import get_last_consultation, get_partner, is_in_chat
from synmed_utils.states import (
    DOC_DIAGNOSIS,
    DOC_INVESTIGATION_ITEM,
    DOC_INVESTIGATION_NEXT,
    DOC_ITEMS,
    DOC_MED_DOSE,
    DOC_MED_DURATION,
    DOC_MED_NAME,
    DOC_MED_NEXT,
    DOC_MED_ROUTE,
    DOC_NOTES,
    DOC_REVIEW,
    LETTER_BODY,
    LETTER_DIAGNOSIS,
    LETTER_REVIEW,
    LETTER_TARGET,
)
from synmed_utils.verified_doctors import is_verified


DOCUMENT_DRAFT_KEY = "clinical_document_draft"
LETTER_DRAFT_KEY = "clinical_letter_draft"


MEDICATION_NEXT_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("Add Another", callback_data="doc_med:add"),
        InlineKeyboardButton("Done", callback_data="doc_med:done"),
    ]
])

INVESTIGATION_NEXT_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("Add Another", callback_data="doc_inv:add"),
        InlineKeyboardButton("Done", callback_data="doc_inv:done"),
    ]
])

LETTER_REVIEW_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("Send", callback_data="letter_review:send")],
    [InlineKeyboardButton("Cancel", callback_data="letter_review:cancel")],
])


def _review_keyboard(draft: dict):
    middle_label = "Edit Medications" if draft["type"] == "prescription" else "Edit Investigations"
    middle_value = "edit medications" if draft["type"] == "prescription" else "edit investigations"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Send", callback_data="doc_review:send")],
        [InlineKeyboardButton("Edit Diagnosis", callback_data="doc_review:edit diagnosis")],
        [InlineKeyboardButton(middle_label, callback_data=f"doc_review:{middle_value}")],
        [InlineKeyboardButton("Edit Notes", callback_data="doc_review:edit notes")],
        [InlineKeyboardButton("Cancel", callback_data="doc_review:cancel")],
    ])


def _get_active_document_context(user_id: int):
    consultation = get_last_consultation(user_id)
    if not consultation:
        return None
    return {
        "consultation_id": consultation["consultation_id"],
        "patient_id": consultation["patient_id"],
        "patient_details": consultation.get("patient_details", {}),
        "doctor_id": consultation["doctor_id"],
    }


def _format_medication_line(index: int, medication: dict) -> str:
    return (
        f"{index}. {medication['route']}    {medication['name']}    "
        f"{medication['dose']}    {medication['duration']}"
    )


def _build_review_text(draft: dict) -> str:
    notes = draft.get("notes") or "None"
    if draft["type"] == "prescription":
        medications = draft.get("medications", [])
        meds_text = (
            "\n".join(
                _format_medication_line(index, medication)
                for index, medication in enumerate(medications, start=1)
            )
            if medications
            else "No medications added."
        )
        item_title = "Prescribed medications"
    else:
        investigation_items = draft.get("investigations", [])
        meds_text = (
            "\n".join(
                f"{index}. {item}"
                for index, item in enumerate(investigation_items, start=1)
            )
            if investigation_items
            else draft.get("items_text", "No investigations added.")
        )
        item_title = "Requested investigations"

    return (
        "Review this draft before sending:\n\n"
        f"Diagnosis:\n{draft.get('diagnosis', 'N/A')}\n\n"
        f"{item_title}:\n{meds_text}\n\n"
        f"Notes:\n{notes}\n\n"
        "Reply with one of these:\n"
        "send\n"
        "edit diagnosis\n"
        "edit medications\n"
        "edit notes\n"
        "cancel"
    )


async def _show_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    draft = context.user_data.get(DOCUMENT_DRAFT_KEY)
    if not draft:
        if update.message:
            await update.message.reply_text("Document session expired.")
        return ConversationHandler.END

    callback_query = getattr(update, "callback_query", None)
    if update.message:
        await update.message.reply_text(
            _build_review_text(draft),
            reply_markup=_review_keyboard(draft),
        )
    elif callback_query:
        await callback_query.message.reply_text(
            _build_review_text(draft),
            reply_markup=_review_keyboard(draft),
        )
    return DOC_REVIEW


async def start_prescription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _start_document_flow(update, context, "prescription")


async def start_investigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _start_document_flow(update, context, "investigation")


async def start_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _start_letter_flow(update, context, "referral")


async def start_medical_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _start_letter_flow(update, context, "medical_report")


async def cancel_document_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop(DOCUMENT_DRAFT_KEY, None)
    callback_query = getattr(update, "callback_query", None)
    if callback_query:
        await callback_query.answer()
        await callback_query.message.reply_text("Document drafting cancelled.")
    elif update.message:
        await update.message.reply_text("Document drafting cancelled.")
    return ConversationHandler.END


async def cancel_letter_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop(LETTER_DRAFT_KEY, None)
    callback_query = getattr(update, "callback_query", None)
    if callback_query:
        await callback_query.answer()
        await callback_query.message.reply_text("Referral / report drafting cancelled.")
    elif update.message:
        await update.message.reply_text("Referral / report drafting cancelled.")
    return ConversationHandler.END


async def _start_document_flow(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    doc_type: str,
):
    if not update.message:
        return ConversationHandler.END
    reset_interactive_state(context.user_data)

    doctor_id = update.effective_user.id
    if not is_verified(doctor_id):
        await update.message.reply_text(
            "Only verified doctors can create clinical documents."
        )
        return ConversationHandler.END

    if not is_in_chat(doctor_id):
        await update.message.reply_text(
            "You need an active consultation to create this document."
        )
        return ConversationHandler.END

    if not get_partner(doctor_id):
        await update.message.reply_text(
            "Unable to find the patient attached to this consultation."
        )
        return ConversationHandler.END

    draft = _get_active_document_context(doctor_id)
    if not draft:
        await update.message.reply_text(
            "Unable to find the current consultation record."
        )
        return ConversationHandler.END

    draft["type"] = doc_type
    draft["medications"] = []
    draft["investigations"] = []
    draft["notes"] = ""
    draft["items_text"] = ""
    draft["diagnosis"] = get_consultation_diagnosis(draft["consultation_id"])
    context.user_data[DOCUMENT_DRAFT_KEY] = draft

    label = "prescription" if doc_type == "prescription" else "investigation request"
    if draft["diagnosis"]:
        await update.message.reply_text(
            f"Creating a {label}.\n"
            "Using the saved consultation diagnosis for this document.\n\n"
            f"Diagnosis: {draft['diagnosis']}"
        )
        if draft["type"] == "prescription":
            await update.message.reply_text(
                "Enter the medication type / route.\n"
                "Example: Tablet / Oral"
            )
            return DOC_MED_ROUTE
        await update.message.reply_text(
            "Enter the name of the first investigation.\n"
            "Example: Full blood count"
        )
        return DOC_INVESTIGATION_ITEM

    await update.message.reply_text(
        f"Creating a {label}.\n"
        "Your draft entries will stay private until the final document is sent.\n\n"
        "Please enter the diagnosis."
    )
    return DOC_DIAGNOSIS


async def _start_letter_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, letter_type: str):
    if not update.message:
        return ConversationHandler.END
    reset_interactive_state(context.user_data)

    doctor_id = update.effective_user.id
    if not is_verified(doctor_id):
        await update.message.reply_text("Only verified doctors can create referral notes or medical reports.")
        return ConversationHandler.END

    if not is_in_chat(doctor_id):
        await update.message.reply_text("You need an active consultation to create this document.")
        return ConversationHandler.END

    draft = _get_active_document_context(doctor_id)
    if not draft:
        await update.message.reply_text("Unable to find the current consultation record.")
        return ConversationHandler.END

    draft["type"] = letter_type
    draft["diagnosis"] = get_consultation_diagnosis(draft["consultation_id"])
    draft["body"] = ""
    draft["target_hospital"] = ""
    context.user_data[LETTER_DRAFT_KEY] = draft

    label = "referral note" if letter_type == "referral" else "medical report"
    if draft["diagnosis"]:
        await update.message.reply_text(
            f"Creating a {label}.\n"
            "Using the saved consultation diagnosis for this document.\n\n"
            f"Diagnosis: {draft['diagnosis']}"
        )
        await update.message.reply_text(
            "Enter the referral note." if letter_type == "referral" else "Enter the medical report."
        )
        return LETTER_BODY

    await update.message.reply_text(f"Creating a {label}.\n\nPlease enter the diagnosis.")
    return LETTER_DIAGNOSIS


async def handle_document_diagnosis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return DOC_DIAGNOSIS

    draft = context.user_data.get(DOCUMENT_DRAFT_KEY)
    if not draft:
        await update.message.reply_text("Document session expired.")
        return ConversationHandler.END

    draft["diagnosis"] = update.message.text.strip()
    set_consultation_diagnosis(draft["consultation_id"], draft["diagnosis"])
    context.user_data[DOCUMENT_DRAFT_KEY] = draft

    if draft["type"] == "prescription":
        await update.message.reply_text(
            "Enter the medication type / route.\n"
            "Example: Tablet / Oral"
        )
        return DOC_MED_ROUTE

    await update.message.reply_text(
        "Enter the name of the first investigation.\n"
        "Example: Full blood count"
    )
    return DOC_INVESTIGATION_ITEM


async def handle_letter_diagnosis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return LETTER_DIAGNOSIS

    draft = context.user_data.get(LETTER_DRAFT_KEY)
    if not draft:
        await update.message.reply_text("Document session expired.")
        return ConversationHandler.END

    draft["diagnosis"] = update.message.text.strip()
    set_consultation_diagnosis(draft["consultation_id"], draft["diagnosis"])
    context.user_data[LETTER_DRAFT_KEY] = draft
    await update.message.reply_text("Enter the referral note." if draft["type"] == "referral" else "Enter the medical report.")
    return LETTER_BODY


async def handle_letter_body(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return LETTER_BODY

    draft = context.user_data.get(LETTER_DRAFT_KEY)
    if not draft:
        await update.message.reply_text("Document session expired.")
        return ConversationHandler.END

    draft["body"] = update.message.text.strip()
    context.user_data[LETTER_DRAFT_KEY] = draft
    if draft["type"] == "referral":
        await update.message.reply_text("Enter the hospital or facility you are referring the patient to.")
        return LETTER_TARGET

    await update.message.reply_text(
        f"Diagnosis: {draft['diagnosis']}\n\n{draft['body']}\n\nReply with send or cancel.",
        reply_markup=LETTER_REVIEW_KEYBOARD,
    )
    return LETTER_REVIEW


async def handle_letter_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return LETTER_TARGET

    draft = context.user_data.get(LETTER_DRAFT_KEY)
    if not draft:
        await update.message.reply_text("Document session expired.")
        return ConversationHandler.END

    draft["target_hospital"] = update.message.text.strip()
    context.user_data[LETTER_DRAFT_KEY] = draft
    await update.message.reply_text(
        f"Diagnosis: {draft['diagnosis']}\n\n{draft['body']}\n\nReferred Hospital: {draft['target_hospital']}\n\nReply with send or cancel.",
        reply_markup=LETTER_REVIEW_KEYBOARD,
    )
    return LETTER_REVIEW


async def handle_letter_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    draft = context.user_data.get(LETTER_DRAFT_KEY)
    if not draft:
        if update.message:
            await update.message.reply_text("Document session expired.")
        return ConversationHandler.END

    callback_query = getattr(update, "callback_query", None)
    if callback_query:
        await callback_query.answer()
        choice = callback_query.data.split(":", 1)[1]
        await callback_query.edit_message_reply_markup(reply_markup=None)
    elif update.message and update.message.text:
        choice = update.message.text.strip().lower()
    else:
        return LETTER_REVIEW

    if choice == "cancel":
        return await cancel_letter_flow(update, context)

    if choice != "send":
        target = callback_query.message if callback_query else update.message
        await target.reply_text("Use Send or Cancel.")
        return LETTER_REVIEW

    if draft["type"] == "referral":
        document = create_referral_document(
            consultation_id=draft["consultation_id"],
            doctor_id=draft["doctor_id"],
            patient_id=draft["patient_id"],
            patient_details=draft["patient_details"],
            diagnosis=draft["diagnosis"],
            referral_note=draft["body"],
            referred_hospital=draft["target_hospital"],
        )
        doc_type_label = "Referral note"
    else:
        document = create_medical_report_document(
            consultation_id=draft["consultation_id"],
            doctor_id=draft["doctor_id"],
            patient_id=draft["patient_id"],
            patient_details=draft["patient_details"],
            diagnosis=draft["diagnosis"],
            report_note=draft["body"],
        )
        doc_type_label = "Medical report"

    await context.bot.send_document(
        chat_id=draft["patient_id"],
        document=document["file"],
        filename=document["filename"],
        caption=f"{doc_type_label} for your consultation.",
    )
    log_consultation_event(
        draft["consultation_id"],
        event_type="document_issued",
        actor_id=str(draft["doctor_id"]),
        details=doc_type_label,
    )
    target = callback_query.message if callback_query else update.message
    await target.reply_text(f"{doc_type_label} created and sent to the patient.")
    context.user_data.pop(LETTER_DRAFT_KEY, None)
    return ConversationHandler.END


async def handle_document_medication_route(update: Update, context: ContextTypes.DEFAULT_TYPE):
    draft = context.user_data.get(DOCUMENT_DRAFT_KEY)
    if not draft or not update.message or not update.message.text:
        return DOC_MED_ROUTE

    draft["current_medication"] = {"route": update.message.text.strip()}
    context.user_data[DOCUMENT_DRAFT_KEY] = draft
    await update.message.reply_text("Enter the name of the medication.")
    return DOC_MED_NAME


async def handle_document_medication_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    draft = context.user_data.get(DOCUMENT_DRAFT_KEY)
    if not draft or not update.message or not update.message.text:
        return DOC_MED_NAME

    draft["current_medication"]["name"] = update.message.text.strip()
    context.user_data[DOCUMENT_DRAFT_KEY] = draft
    await update.message.reply_text("Enter the dose.\nExample: 500mg twice daily")
    return DOC_MED_DOSE


async def handle_document_medication_dose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    draft = context.user_data.get(DOCUMENT_DRAFT_KEY)
    if not draft or not update.message or not update.message.text:
        return DOC_MED_DOSE

    draft["current_medication"]["dose"] = update.message.text.strip()
    context.user_data[DOCUMENT_DRAFT_KEY] = draft
    await update.message.reply_text("Enter the duration.\nExample: 5 days")
    return DOC_MED_DURATION


async def handle_document_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    draft = context.user_data.get(DOCUMENT_DRAFT_KEY)
    if not draft or not update.message or not update.message.text:
        return DOC_MED_DURATION

    medication = draft.get("current_medication", {})
    medication["duration"] = update.message.text.strip()
    draft.setdefault("medications", []).append(medication)
    draft.pop("current_medication", None)
    context.user_data[DOCUMENT_DRAFT_KEY] = draft

    await update.message.reply_text(
        "Medication added.\n"
        "Tap an option below to add another medication or continue to notes.",
        reply_markup=MEDICATION_NEXT_KEYBOARD,
    )
    return DOC_MED_NEXT


async def handle_document_medication_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    draft = context.user_data.get(DOCUMENT_DRAFT_KEY)
    if not draft:
        return DOC_MED_NEXT

    callback_query = getattr(update, "callback_query", None)
    if callback_query:
        await callback_query.answer()
        choice = callback_query.data.split(":", 1)[1]
        await callback_query.edit_message_reply_markup(reply_markup=None)
    elif update.message and update.message.text:
        choice = update.message.text.strip().lower()
    else:
        return DOC_MED_NEXT

    if choice == "add":
        target = callback_query.message if callback_query else update.message
        await target.reply_text(
            "Enter the medication type / route.\n"
            "Example: Syrup / Oral"
        )
        return DOC_MED_ROUTE

    if choice == "done":
        target = callback_query.message if callback_query else update.message
        await target.reply_text(
            "Add any extra notes, or reply with skip if there are none."
        )
        return DOC_NOTES

    if update.message:
        await update.message.reply_text("Use the buttons below, or reply with `add` or `done`.")
    return DOC_MED_NEXT


async def handle_document_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return DOC_ITEMS

    draft = context.user_data.get(DOCUMENT_DRAFT_KEY)
    if not draft:
        await update.message.reply_text("Document session expired.")
        return ConversationHandler.END

    draft["items_text"] = update.message.text.strip()
    context.user_data[DOCUMENT_DRAFT_KEY] = draft
    await update.message.reply_text(
        "Add any extra notes, or reply with skip if there are none."
    )
    return DOC_NOTES


async def handle_document_investigation_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return DOC_INVESTIGATION_ITEM

    draft = context.user_data.get(DOCUMENT_DRAFT_KEY)
    if not draft:
        await update.message.reply_text("Document session expired.")
        return ConversationHandler.END

    item = update.message.text.strip()
    draft.setdefault("investigations", []).append(item)
    draft["items_text"] = "\n".join(draft["investigations"])
    context.user_data[DOCUMENT_DRAFT_KEY] = draft

    await update.message.reply_text(
        "Investigation added.\n"
        "Tap an option below to add another investigation or continue to notes.",
        reply_markup=INVESTIGATION_NEXT_KEYBOARD,
    )
    return DOC_INVESTIGATION_NEXT


async def handle_document_investigation_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    draft = context.user_data.get(DOCUMENT_DRAFT_KEY)
    if not draft:
        if update.message:
            await update.message.reply_text("Document session expired.")
        return ConversationHandler.END

    callback_query = getattr(update, "callback_query", None)
    if callback_query:
        await callback_query.answer()
        choice = callback_query.data.split(":", 1)[1]
        await callback_query.edit_message_reply_markup(reply_markup=None)
    elif update.message and update.message.text:
        choice = update.message.text.strip().lower()
    else:
        return DOC_INVESTIGATION_NEXT

    if choice == "add":
        target = callback_query.message if callback_query else update.message
        await target.reply_text(
            "Enter the next investigation.\n"
            "Example: Urinalysis"
        )
        return DOC_INVESTIGATION_ITEM

    if choice == "done":
        target = callback_query.message if callback_query else update.message
        await target.reply_text(
            "Add any extra notes, or reply with skip if there are none."
        )
        return DOC_NOTES

    if update.message:
        await update.message.reply_text("Use the buttons below, or reply with `add` or `done`.")
    return DOC_INVESTIGATION_NEXT


async def handle_document_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return DOC_NOTES

    draft = context.user_data.get(DOCUMENT_DRAFT_KEY)
    if not draft:
        await update.message.reply_text("Document session expired.")
        return ConversationHandler.END

    notes = update.message.text.strip()
    draft["notes"] = "" if notes.lower() == "skip" else notes
    context.user_data[DOCUMENT_DRAFT_KEY] = draft
    return await _show_review(update, context)


async def handle_document_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    draft = context.user_data.get(DOCUMENT_DRAFT_KEY)
    if not draft:
        if update.message:
            await update.message.reply_text("Document session expired.")
        return ConversationHandler.END

    callback_query = getattr(update, "callback_query", None)
    if callback_query:
        await callback_query.answer()
        choice = callback_query.data.split(":", 1)[1]
        await callback_query.edit_message_reply_markup(reply_markup=None)
    elif update.message and update.message.text:
        choice = update.message.text.strip().lower()
    else:
        return DOC_REVIEW

    if choice == "send":
        if draft["type"] == "prescription":
            document = create_prescription_document(
                consultation_id=draft["consultation_id"],
                doctor_id=draft["doctor_id"],
                patient_id=draft["patient_id"],
                patient_details=draft["patient_details"],
                diagnosis=draft["diagnosis"],
                medications=draft.get("medications", []),
                notes=draft.get("notes", ""),
            )
            doc_type_label = "Prescription"
        else:
            document = create_investigation_document(
                consultation_id=draft["consultation_id"],
                doctor_id=draft["doctor_id"],
                patient_id=draft["patient_id"],
                patient_details=draft["patient_details"],
                diagnosis=draft["diagnosis"],
                tests_text=draft.get("items_text", ""),
                notes=draft.get("notes", ""),
            )
            doc_type_label = "Investigation request"

        if draft["patient_details"].get("source") != "web":
            await context.bot.send_document(
                chat_id=draft["patient_id"],
                document=document["file"],
                filename=document["filename"],
                caption=f"{doc_type_label} for your consultation.",
            )
        log_consultation_event(
            draft["consultation_id"],
            event_type="document_issued",
            actor_id=str(draft["doctor_id"]),
            details=doc_type_label,
        )
        target = callback_query.message if callback_query else update.message
        await target.reply_text(
            (
                f"{doc_type_label} created and sent to the patient."
                if draft["patient_details"].get("source") != "web"
                else f"{doc_type_label} created successfully. The web patient can view it in the consultation room."
            )
        )
        context.user_data.pop(DOCUMENT_DRAFT_KEY, None)
        return ConversationHandler.END

    if choice == "edit diagnosis":
        target = callback_query.message if callback_query else update.message
        await target.reply_text("Please re-enter the diagnosis.")
        return DOC_DIAGNOSIS

    if choice == "edit medications":
        if draft["type"] == "prescription":
            draft["medications"] = []
            draft.pop("current_medication", None)
            context.user_data[DOCUMENT_DRAFT_KEY] = draft
            target = callback_query.message if callback_query else update.message
            await target.reply_text(
                "Medication list cleared.\n"
                "Enter the medication type / route for the first medication."
            )
            return DOC_MED_ROUTE

    if choice == "edit investigations":
        draft["investigations"] = []
        draft["items_text"] = ""
        context.user_data[DOCUMENT_DRAFT_KEY] = draft
        target = callback_query.message if callback_query else update.message
        await target.reply_text(
            "Investigation list cleared.\n"
            "Enter the first investigation."
        )
        return DOC_INVESTIGATION_ITEM

    if choice == "edit notes":
        target = callback_query.message if callback_query else update.message
        await target.reply_text(
            "Please re-enter the notes, or reply with skip."
        )
        return DOC_NOTES

    if choice == "cancel":
        return await cancel_document_flow(update, context)

    if update.message:
        await update.message.reply_text(
            "Use the buttons below, or reply with `send`, `edit diagnosis`, `edit medications`, `edit investigations`, `edit notes`, or `cancel`."
        )
    return DOC_REVIEW
