from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from services.admin_audit import get_recent_admin_actions, log_admin_action
from services.clinical_documents import (
    load_existing_document_bytes,
    regenerate_investigation_document,
    regenerate_prescription_document,
)
from services.consultation_records import (
    export_consultation_file,
    get_consultation_document_records,
    get_latest_consultation_bundle,
)
from services.patient_records import (
    get_patient_by_identifier,
    patient_summary,
    search_patient_records,
    update_patient_record,
)
from services.paystack import (
    get_payment_by_reference,
    grant_manual_payment_override,
    mark_payment_verified,
)
from synmed_utils.admin import is_admin
from synmed_utils.support_registry import is_support_approved


ADMIN_PENDING_ACTION_KEY = "admin_pending_action"
PATIENT_LOOKUP_ACTION = "patient_record_lookup"
PATIENT_EDIT_IDENTIFIER_ACTION = "patient_edit_identifier"
PATIENT_EDIT_FIELD_ACTION = "patient_edit_field"
PATIENT_EDIT_VALUE_ACTION = "patient_edit_value"
PATIENT_SEARCH_ACTION = "patient_record_search"
CONSULTATION_EXPORT_ACTION = "consultation_export"
PATIENT_EDIT_DATA_KEY = "admin_patient_edit_data"
CONSULTATION_MENU_ACTION = "consultation_menu_lookup"
PATIENT_DOCS_MENU_ACTION = "patient_docs_menu_lookup"
PAYMENT_ISSUES_MENU_ACTION = "payment_issues_menu_lookup"


def has_records_access(user_id: int) -> bool:
    return is_admin(user_id) or is_support_approved(user_id)


def _access_denied_text() -> str:
    return "Admin or approved customer-care-only command."


def _actor_label(user_id: int) -> str:
    return "admin" if is_admin(user_id) else "support"


def _document_caption(kind: str, consultation_id: str) -> str:
    label = {
        "prescription": "Prescription",
        "investigation": "Investigation Request",
        "referral": "Referral Note",
        "medical_report": "Medical Report",
    }.get(kind, kind.replace("_", " ").title())
    return f"{label} | Consultation {consultation_id[:8]}"


def _consultation_menu_keyboard(identifier: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Download Consultation", callback_data=f"adminmenu:consultation:export:{identifier}")],
            [InlineKeyboardButton("Consultation Bundle", callback_data=f"adminmenu:consultation:bundle:{identifier}")],
            [InlineKeyboardButton("Resend Docs To Admin", callback_data=f"adminmenu:consultation:docs_admin:{identifier}")],
            [InlineKeyboardButton("Resend Docs To Patient", callback_data=f"adminmenu:consultation:docs_patient:{identifier}")],
        ]
    )


def _patient_docs_menu_keyboard(identifier: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Prescription", callback_data=f"adminmenu:docs_kind:prescription:{identifier}")],
            [InlineKeyboardButton("Investigation", callback_data=f"adminmenu:docs_kind:investigation:{identifier}")],
            [InlineKeyboardButton("All Documents", callback_data=f"adminmenu:docs_kind:all:{identifier}")],
        ]
    )


def _patient_docs_action_keyboard(identifier: str, kind: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Preview / Download", callback_data=f"adminmenu:docs_action:{kind}:admin:{identifier}")],
            [InlineKeyboardButton("Send To Patient", callback_data=f"adminmenu:docs_action:{kind}:patient:{identifier}")],
        ]
    )


def _payment_issues_keyboard(identifier: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Allow Consultation To Proceed", callback_data=f"adminmenu:payment:force:{identifier}")],
            [InlineKeyboardButton("View Patient Record", callback_data=f"adminmenu:payment:patient:{identifier}")],
        ]
    )


async def _send_document_record(*, context, chat_id: int, bundle: dict, item: dict):
    patient = bundle["patient"]
    row = item["row"]
    kind = item["kind"]
    file_buffer = load_existing_document_bytes(item["asset_path"])
    if file_buffer is None:
        patient_details = {
            "hospital_number": patient["patient_id"] if patient else bundle["consultation"]["patient_id"],
            "name": patient["name"] if patient else "N/A",
            "age": patient["age"] if patient else "N/A",
            "gender": patient["gender"] if patient else "N/A",
            "phone": patient["phone"] if patient else "N/A",
            "address": patient["address"] if patient else "N/A",
            "allergy": patient["allergy"] if patient else "",
            "medical_conditions": patient["medical_conditions"] if patient else "",
            "history": bundle["consultation"]["notes"] or "N/A",
        }
        if kind == "prescription":
            regenerated = regenerate_prescription_document(row, patient_details)
        elif kind == "investigation":
            regenerated = regenerate_investigation_document(row, patient_details)
        else:
            raise ValueError("Only prescription and investigation documents can be regenerated right now.")
        file_buffer = regenerated["file"]

    await context.bot.send_document(
        chat_id=chat_id,
        document=file_buffer,
        filename=file_buffer.name,
        caption=_document_caption(kind, bundle["consultation"]["consultation_id"]),
    )


async def patient_record_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not has_records_access(update.effective_user.id):
        await update.message.reply_text(_access_denied_text())
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /patient_record <hospital_number_or_phone>"
        )
        return

    patient = get_patient_by_identifier(" ".join(context.args))
    if not patient:
        await update.message.reply_text("Patient record not found.")
        return

    log_admin_action(
        admin_id=update.effective_user.id,
        action="view_patient_record",
        target_type="patient",
        target_id=patient["hospital_number"],
        details=f"Viewed by {_actor_label(update.effective_user.id)} command",
    )
    await update.message.reply_text(patient_summary(patient))


async def consultation_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if not has_records_access(update.effective_user.id):
        await update.message.reply_text(_access_denied_text())
        return
    context.user_data[ADMIN_PENDING_ACTION_KEY] = CONSULTATION_MENU_ACTION
    await update.message.reply_text(
        "Enter the consultation ID or patient hospital number."
    )


async def patient_docs_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if not has_records_access(update.effective_user.id):
        await update.message.reply_text(_access_denied_text())
        return
    context.user_data[ADMIN_PENDING_ACTION_KEY] = PATIENT_DOCS_MENU_ACTION
    await update.message.reply_text(
        "Enter the consultation ID or patient hospital number to open document options."
    )


async def payment_issues_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin-only command.")
        return
    context.user_data[ADMIN_PENDING_ACTION_KEY] = PAYMENT_ISSUES_MENU_ACTION
    await update.message.reply_text(
        "Enter the patient hospital number for the payment issue."
    )


async def handle_admin_followup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    if not has_records_access(update.effective_user.id):
        return

    pending_action = context.user_data.get(ADMIN_PENDING_ACTION_KEY)
    if pending_action == PATIENT_LOOKUP_ACTION:
        context.user_data.pop(ADMIN_PENDING_ACTION_KEY, None)
        patient = get_patient_by_identifier(update.message.text.strip())
        if not patient:
            await update.message.reply_text("Patient record not found.")
            return

        log_admin_action(
            admin_id=update.effective_user.id,
            action="view_patient_record",
            target_type="patient",
            target_id=patient["hospital_number"],
            details=f"Viewed via dashboard by {_actor_label(update.effective_user.id)}",
        )
        await update.message.reply_text(patient_summary(patient))
        return

    if pending_action == PATIENT_SEARCH_ACTION:
        context.user_data.pop(ADMIN_PENDING_ACTION_KEY, None)
        patients = search_patient_records(update.message.text.strip())
        if not patients:
            await update.message.reply_text("No matching patient records found.")
            return

        lines = ["Matching Patient Records", ""]
        for patient in patients:
            lines.append(
                f"{patient['hospital_number']} | {patient['name']} | {patient['phone']}"
            )
        await update.message.reply_text("\n".join(lines))
        log_admin_action(
            admin_id=update.effective_user.id,
            action="search_patient_records",
            target_type="patient_search",
            target_id=update.message.text.strip(),
            details=f"Matches: {len(patients)}",
        )
        return

    if pending_action == CONSULTATION_MENU_ACTION:
        context.user_data.pop(ADMIN_PENDING_ACTION_KEY, None)
        bundle = get_latest_consultation_bundle(update.message.text.strip())
        if not bundle:
            await update.message.reply_text("Consultation record not found.")
            return
        consultation = bundle["consultation"]
        patient = bundle["patient"]
        text = (
            "Consultation Menu\n\n"
            f"Consultation ID: {consultation['consultation_id']}\n"
            f"Hospital Number: {consultation['patient_id']}\n"
            f"Patient: {patient['name'] if patient else 'N/A'}\n"
            f"Status: {consultation['status']}\n"
            f"Diagnosis: {consultation['diagnosis'] or 'Not recorded'}"
        )
        await update.message.reply_text(
            text,
            reply_markup=_consultation_menu_keyboard(update.message.text.strip()),
        )
        return

    if pending_action == PATIENT_DOCS_MENU_ACTION:
        context.user_data.pop(ADMIN_PENDING_ACTION_KEY, None)
        records = get_consultation_document_records(update.message.text.strip())
        if not records or not records["documents"]:
            await update.message.reply_text("No previous clinical documents found.")
            return
        await update.message.reply_text(
            f"Found {len(records['documents'])} document(s) for consultation {records['consultation_id'][:8]}.",
            reply_markup=_patient_docs_menu_keyboard(update.message.text.strip()),
        )
        return

    if pending_action == PAYMENT_ISSUES_MENU_ACTION:
        context.user_data.pop(ADMIN_PENDING_ACTION_KEY, None)
        patient = get_patient_by_identifier(update.message.text.strip())
        if not patient:
            await update.message.reply_text("Patient record not found.")
            return
        await update.message.reply_text(
            "Payment Issues Menu\n\n"
            f"{patient_summary(patient)}",
            reply_markup=_payment_issues_keyboard(patient["hospital_number"]),
        )
        return

    if pending_action == CONSULTATION_EXPORT_ACTION:
        context.user_data.pop(ADMIN_PENDING_ACTION_KEY, None)
        export = export_consultation_file(update.message.text.strip())
        if not export:
            await update.message.reply_text("Consultation record not found.")
            return

        await context.bot.send_document(
            chat_id=update.effective_user.id,
            document=export["file"],
            filename=export["filename"],
            caption=f"Consultation export: {export['consultation_id']}",
        )
        log_admin_action(
            admin_id=update.effective_user.id,
            action="export_consultation",
            target_type="consultation",
            target_id=export["consultation_id"],
            details=f"Exported consultation transcript via dashboard by {_actor_label(update.effective_user.id)}",
        )
        return

    if pending_action == PATIENT_EDIT_IDENTIFIER_ACTION:
        patient = get_patient_by_identifier(update.message.text.strip())
        if not patient:
            await update.message.reply_text("Patient record not found.")
            return

        context.user_data[ADMIN_PENDING_ACTION_KEY] = PATIENT_EDIT_FIELD_ACTION
        context.user_data[PATIENT_EDIT_DATA_KEY] = {
            "identifier": patient["hospital_number"],
        }
        await update.message.reply_text(
            "Which field do you want to edit?\n"
            "Reply with one of: name, age, gender, phone, email, address, allergy, medical_conditions."
        )
        return

    if pending_action == PATIENT_EDIT_FIELD_ACTION:
        field = update.message.text.strip().lower()
        allowed_fields = {
            "name",
            "age",
            "gender",
            "phone",
            "email",
            "address",
            "allergy",
            "medical_conditions",
        }
        if field not in allowed_fields:
            await update.message.reply_text(
                "Invalid field. Reply with one of: name, age, gender, phone, email, address, allergy, medical_conditions."
            )
            return

        edit_data = context.user_data.get(PATIENT_EDIT_DATA_KEY, {})
        edit_data["field"] = field
        context.user_data[PATIENT_EDIT_DATA_KEY] = edit_data
        context.user_data[ADMIN_PENDING_ACTION_KEY] = PATIENT_EDIT_VALUE_ACTION
        await update.message.reply_text(
            f"Enter the new value for `{field}`.",
            parse_mode="Markdown",
        )
        return

    if pending_action == PATIENT_EDIT_VALUE_ACTION:
        edit_data = context.user_data.get(PATIENT_EDIT_DATA_KEY, {})
        identifier = edit_data.get("identifier")
        field = edit_data.get("field")
        if not identifier or not field:
            context.user_data.pop(ADMIN_PENDING_ACTION_KEY, None)
            context.user_data.pop(PATIENT_EDIT_DATA_KEY, None)
            await update.message.reply_text("Edit session expired.")
            return

        try:
            patient = update_patient_record(identifier, field, update.message.text.strip())
        except ValueError:
            await update.message.reply_text(
                "Allowed fields: name, age, gender, phone, email, address, allergy, medical_conditions."
            )
            return

        context.user_data.pop(ADMIN_PENDING_ACTION_KEY, None)
        context.user_data.pop(PATIENT_EDIT_DATA_KEY, None)
        if not patient:
            await update.message.reply_text("Patient record not found.")
            return

        await update.message.reply_text(
            "Patient record updated.\n\n"
            f"{patient_summary(patient)}"
        )
        log_admin_action(
            admin_id=update.effective_user.id,
            action="edit_patient_record",
            target_type="patient",
            target_id=patient["hospital_number"],
            details=f"Updated field: {field}",
        )


async def edit_patient_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not has_records_access(update.effective_user.id):
        await update.message.reply_text(_access_denied_text())
        return

    payload = " ".join(context.args)
    parts = [part.strip() for part in payload.split("|")]
    if len(parts) != 3:
        await update.message.reply_text(
            "Usage: /edit_patient <hospital_number_or_phone> | <field> | <value>"
        )
        return

    identifier, field, value = parts
    try:
        patient = update_patient_record(identifier, field, value)
    except ValueError:
        await update.message.reply_text(
            "Allowed fields: name, age, gender, phone, email, address, allergy, medical_conditions."
        )
        return

    if not patient:
        await update.message.reply_text("Patient record not found.")
        return

    await update.message.reply_text(
        "Patient record updated.\n\n"
        f"{patient_summary(patient)}"
    )
    log_admin_action(
        admin_id=update.effective_user.id,
        action="edit_patient_record",
        target_type="patient",
        target_id=patient["hospital_number"],
        details=f"Updated field: {field}",
    )


async def search_records_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not has_records_access(update.effective_user.id):
        await update.message.reply_text(_access_denied_text())
        return

    if not context.args:
        await update.message.reply_text("Usage: /search_records <name_or_phone_or_hospital_number>")
        return

    query = " ".join(context.args)
    patients = search_patient_records(query)
    if not patients:
        await update.message.reply_text("No matching patient records found.")
        return

    lines = ["Matching Patient Records", ""]
    for patient in patients:
        lines.append(
            f"{patient['hospital_number']} | {patient['name']} | {patient['phone']}"
        )
    await update.message.reply_text("\n".join(lines))
    log_admin_action(
        admin_id=update.effective_user.id,
        action="search_patient_records",
        target_type="patient_search",
        target_id=query,
        details=f"Matches: {len(patients)}",
    )


async def audit_log_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin-only command.")
        return

    entries = get_recent_admin_actions()
    if not entries:
        await update.message.reply_text("No admin audit entries yet.")
        return

    lines = ["Recent Admin Audit Log", ""]
    for entry in entries:
        lines.append(
            f"{entry['created_at']} | admin {entry['admin_id']} | {entry['action']} | {entry['target_type']}:{entry['target_id']}"
        )
    await update.message.reply_text("\n".join(lines))


async def export_consultation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not has_records_access(update.effective_user.id):
        await update.message.reply_text(_access_denied_text())
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /export_consultation <consultation_id_or_hospital_number>"
        )
        return

    export = export_consultation_file(" ".join(context.args))
    if not export:
        await update.message.reply_text("Consultation record not found.")
        return

    await context.bot.send_document(
        chat_id=update.effective_user.id,
        document=export["file"],
        filename=export["filename"],
        caption=f"Consultation export: {export['consultation_id']}",
    )
    log_admin_action(
        admin_id=update.effective_user.id,
        action="export_consultation",
        target_type="consultation",
        target_id=export["consultation_id"],
        details=f"Exported consultation transcript by {_actor_label(update.effective_user.id)}",
    )


async def consultation_bundle_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not has_records_access(update.effective_user.id):
        await update.message.reply_text(_access_denied_text())
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /consultation_bundle <consultation_id_or_hospital_number>"
        )
        return

    identifier = " ".join(context.args)
    bundle = get_latest_consultation_bundle(identifier)
    export = export_consultation_file(identifier)
    if not bundle or not export:
        await update.message.reply_text("Consultation record not found.")
        return

    consultation = bundle["consultation"]
    await context.bot.send_document(
        chat_id=update.effective_user.id,
        document=export["file"],
        filename=export["filename"],
        caption=f"Consultation bundle summary: {consultation['consultation_id']}",
    )

    sent_docs = 0
    records = get_consultation_document_records(identifier)
    if records:
        for item in records["documents"]:
            if item["kind"] in {"prescription", "investigation"}:
                await _send_document_record(
                    context=context,
                    chat_id=update.effective_user.id,
                    bundle=bundle,
                    item=item,
                )
                sent_docs += 1
                continue

            if item["kind"] in {"referral", "medical_report"}:
                file_buffer = load_existing_document_bytes(item["asset_path"])
                if not file_buffer:
                    continue
                await context.bot.send_document(
                    chat_id=update.effective_user.id,
                    document=file_buffer,
                    filename=file_buffer.name,
                    caption=_document_caption(item["kind"], consultation["consultation_id"]),
                )
                sent_docs += 1

    await update.message.reply_text(
        f"Consultation bundle ready.\n"
        f"Saved consultation: {consultation['saved_at'] or 'Not explicitly saved'}\n"
        f"Documents attached: {sent_docs}"
    )
    log_admin_action(
        admin_id=update.effective_user.id,
        action="consultation_bundle",
        target_type="consultation",
        target_id=consultation["consultation_id"],
        details=f"{_actor_label(update.effective_user.id)} downloaded consultation bundle",
    )


async def resend_documents_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not has_records_access(update.effective_user.id):
        await update.message.reply_text(_access_denied_text())
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /resend_docs <consultation_id_or_hospital_number> [patient]\n"
            "Add `patient` at the end if you also want the document sent to the patient."
        )
        return

    args = list(context.args)
    send_to_patient = args[-1].lower() == "patient"
    if send_to_patient:
        args = args[:-1]
    identifier = " ".join(args).strip()
    if not identifier:
        await update.message.reply_text("Please provide the consultation ID or hospital number.")
        return

    bundle = get_latest_consultation_bundle(identifier)
    records = get_consultation_document_records(identifier)
    if not bundle or not records or not records["documents"]:
        await update.message.reply_text("No previous documents were found for that consultation.")
        return

    patient_chat_id = bundle["patient"]["telegram_id"] if bundle["patient"] else None
    resent = 0
    for item in records["documents"]:
        if item["kind"] not in {"prescription", "investigation"}:
            continue
        await _send_document_record(
            context=context,
            chat_id=update.effective_user.id,
            bundle=bundle,
            item=item,
        )
        resent += 1
        if send_to_patient and patient_chat_id:
            await _send_document_record(
                context=context,
                chat_id=patient_chat_id,
                bundle=bundle,
                item=item,
            )

    if not resent:
        await update.message.reply_text(
            "Only prescription and investigation files can be resent or regenerated from this command right now."
        )
        return

    await update.message.reply_text(
        f"Resent {resent} document(s){' to you and the patient' if send_to_patient and patient_chat_id else ' to you'}."
    )
    log_admin_action(
        admin_id=update.effective_user.id,
        action="resend_clinical_documents",
        target_type="consultation",
        target_id=bundle["consultation"]["consultation_id"],
        details=f"{_actor_label(update.effective_user.id)} resent {resent} document(s)",
    )


async def force_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin-only command.")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /force_payment <hospital_number> [payment_reference]"
        )
        return

    identifier = context.args[0]
    reference = context.args[1] if len(context.args) > 1 else None
    patient = get_patient_by_identifier(identifier)
    if not patient:
        await update.message.reply_text("Patient record not found.")
        return

    if reference and get_payment_by_reference(reference):
        token = mark_payment_verified(
            reference,
            paystack_status="manual_override",
            patient_id=patient["hospital_number"],
        )
    else:
        token = grant_manual_payment_override(
            telegram_id=patient.get("telegram_id") or 0,
            patient_id=patient["hospital_number"],
            email=patient.get("email") or "",
            amount=3000,
            label="SynMed Admin Manual Consultation Approval",
            patient_type="returning",
            reference=reference,
        )

    await update.message.reply_text(
        "Consultation payment override granted.\n\n"
        f"Patient: {patient['hospital_number']} - {patient['name']}\n"
        f"Payment code: {token}\n"
        "This code will work for the next 24 hours."
    )
    log_admin_action(
        admin_id=update.effective_user.id,
        action="force_consultation_payment",
        target_type="patient",
        target_id=patient["hospital_number"],
        details=f"Manual payment override granted. Reference: {reference or 'manual-generated'}",
    )


async def admin_records_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not has_records_access(query.from_user.id):
        await query.edit_message_text(_access_denied_text())
        return

    parts = query.data.split(":")
    if len(parts) < 4:
        await query.edit_message_text("Action could not be understood.")
        return

    _, scope = parts[0], parts[1]

    if scope == "docs_kind":
        _, _, kind, identifier = parts
        label = {
            "prescription": "prescription",
            "investigation": "investigation",
            "all": "all documents",
        }.get(kind, kind)
        await query.edit_message_text(
            f"Choose what to do with the {label}.",
            reply_markup=_patient_docs_action_keyboard(identifier, kind),
        )
        return

    if scope == "docs_action":
        if len(parts) != 5:
            await query.edit_message_text("Action could not be understood.")
            return
        _, _, kind, action, identifier = parts
    else:
        try:
            _, scope, action, identifier = parts
        except ValueError:
            await query.edit_message_text("Action could not be understood.")
            return

    if scope == "consultation" and action == "export":
        export = export_consultation_file(identifier)
        if not export:
            await query.edit_message_text("Consultation record not found.")
            return
        await context.bot.send_document(
            chat_id=query.from_user.id,
            document=export["file"],
            filename=export["filename"],
            caption=f"Consultation export: {export['consultation_id']}",
        )
        await query.edit_message_text("Consultation export sent.")
        return

    if scope == "consultation" and action == "bundle":
        bundle = get_latest_consultation_bundle(identifier)
        export = export_consultation_file(identifier)
        if not bundle or not export:
            await query.edit_message_text("Consultation record not found.")
            return
        await context.bot.send_document(
            chat_id=query.from_user.id,
            document=export["file"],
            filename=export["filename"],
            caption=f"Consultation bundle summary: {bundle['consultation']['consultation_id']}",
        )
        records = get_consultation_document_records(identifier)
        sent_docs = 0
        if records:
            for item in records["documents"]:
                if item["kind"] in {"prescription", "investigation"}:
                    await _send_document_record(context=context, chat_id=query.from_user.id, bundle=bundle, item=item)
                    sent_docs += 1
                elif item["kind"] in {"referral", "medical_report"}:
                    file_buffer = load_existing_document_bytes(item["asset_path"])
                    if file_buffer:
                        await context.bot.send_document(
                            chat_id=query.from_user.id,
                            document=file_buffer,
                            filename=file_buffer.name,
                            caption=_document_caption(item["kind"], bundle["consultation"]["consultation_id"]),
                        )
                        sent_docs += 1
        await query.edit_message_text(f"Consultation bundle sent. Documents attached: {sent_docs}.")
        return

    if scope in {"consultation", "docs_action"} and action in {"docs_admin", "admin", "docs_patient", "patient"}:
        bundle = get_latest_consultation_bundle(identifier)
        records = get_consultation_document_records(identifier)
        if not bundle or not records or not records["documents"]:
            await query.edit_message_text("No previous documents were found.")
            return
        send_to_patient = action in {"docs_patient", "patient"}
        patient_chat_id = bundle["patient"]["telegram_id"] if bundle["patient"] else None
        resent = 0
        for item in records["documents"]:
            if item["kind"] not in {"prescription", "investigation"}:
                continue
            if scope == "docs_action" and kind != "all" and item["kind"] != kind:
                continue
            await _send_document_record(context=context, chat_id=query.from_user.id, bundle=bundle, item=item)
            resent += 1
            if send_to_patient and patient_chat_id:
                await _send_document_record(context=context, chat_id=patient_chat_id, bundle=bundle, item=item)
        if not resent:
            await query.edit_message_text("No matching documents were found for that selection.")
            return
        kind_label = "document(s)" if scope != "docs_action" or kind == "all" else f"{kind} document(s)"
        await query.edit_message_text(
            f"Sent {resent} {kind_label}{' to admin and patient' if send_to_patient and patient_chat_id else ' to admin'}."
        )
        return

    if scope == "payment" and action == "force":
        if not is_admin(query.from_user.id):
            await query.edit_message_text("Admin-only action.")
            return
        patient = get_patient_by_identifier(identifier)
        if not patient:
            await query.edit_message_text("Patient record not found.")
            return
        token = grant_manual_payment_override(
            telegram_id=patient.get("telegram_id") or 0,
            patient_id=patient["hospital_number"],
            email=patient.get("email") or "",
            amount=3000,
            label="SynMed Admin Manual Consultation Approval",
            patient_type="returning",
        )
        await query.edit_message_text(
            "Consultation override granted.\n\n"
            f"Patient: {patient['hospital_number']} - {patient['name']}\n"
            f"Payment code: {token}"
        )
        return

    if scope == "payment" and action == "patient":
        patient = get_patient_by_identifier(identifier)
        if not patient:
            await query.edit_message_text("Patient record not found.")
            return
        await query.edit_message_text(patient_summary(patient))
        return

    await query.edit_message_text("Action could not be completed.")
