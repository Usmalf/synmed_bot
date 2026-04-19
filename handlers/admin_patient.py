from telegram import Update
from telegram.ext import ContextTypes

from services.admin_audit import get_recent_admin_actions, log_admin_action
from services.consultation_records import export_consultation_file
from services.patient_records import (
    get_patient_by_identifier,
    patient_summary,
    search_patient_records,
    update_patient_record,
)
from synmed_utils.admin import is_admin


ADMIN_PENDING_ACTION_KEY = "admin_pending_action"
PATIENT_LOOKUP_ACTION = "patient_record_lookup"
PATIENT_EDIT_IDENTIFIER_ACTION = "patient_edit_identifier"
PATIENT_EDIT_FIELD_ACTION = "patient_edit_field"
PATIENT_EDIT_VALUE_ACTION = "patient_edit_value"
PATIENT_SEARCH_ACTION = "patient_record_search"
CONSULTATION_EXPORT_ACTION = "consultation_export"
PATIENT_EDIT_DATA_KEY = "admin_patient_edit_data"


async def patient_record_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin-only command.")
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
        details="Viewed by direct command",
    )
    await update.message.reply_text(patient_summary(patient))


async def handle_admin_followup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    if not is_admin(update.effective_user.id):
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
            details="Viewed via admin dashboard",
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
            details="Exported consultation transcript",
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
            "Reply with one of: name, age, gender, phone, address, allergy."
        )
        return

    if pending_action == PATIENT_EDIT_FIELD_ACTION:
        field = update.message.text.strip().lower()
        allowed_fields = {"name", "age", "gender", "phone", "address", "allergy"}
        if field not in allowed_fields:
            await update.message.reply_text(
                "Invalid field. Reply with one of: name, age, gender, phone, address, allergy."
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
                "Allowed fields: name, age, gender, phone, address, allergy."
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
        return


async def edit_patient_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin-only command.")
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
            "Allowed fields: name, age, gender, phone, address, allergy."
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

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin-only command.")
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

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin-only command.")
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
        details="Exported consultation transcript",
    )
