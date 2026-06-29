from telegram import Update
from telegram.ext import ContextTypes

import synmed_utils.doctor_registry as registry
from synmed_utils.admin import is_admin
from synmed_utils.doctor_profiles import create_or_update_profile
from synmed_utils.pending_doctors import pending_doctors
from synmed_utils.verified_doctors import add_verified_doctor, is_verified


async def approve_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.answer("Admin only action.", show_alert=True)
        return

    try:
        action, raw_doctor_id = query.data.split(":")
        doctor_id = int(raw_doctor_id)
    except ValueError:
        await query.edit_message_text("Invalid callback data.")
        return

    if doctor_id not in pending_doctors:
        await query.edit_message_text("Request already processed.")
        return

    doctor_info = pending_doctors.get(doctor_id, {})
    doctor_name = doctor_info.get("name", "Unknown Doctor")

    if action == "approve":
        if is_verified(doctor_id):
            pending_doctors.pop(doctor_id, None)
            await query.edit_message_text(
                f"Doctor already verified.\n\n"
                f"Name: {doctor_name}\n"
                f"User ID: {doctor_id}"
            )
            return

        add_verified_doctor(doctor_id)
        create_or_update_profile(doctor_id, {"verified": True})
        pending_doctors.pop(doctor_id, None)
        registry.set_doctor_available(doctor_id)

        await context.bot.send_message(
            chat_id=doctor_id,
            text=(
                "Doctor Verification Approved!\n\n"
                "You are now a verified doctor on SynMed.\n\n"
                "To start receiving consultations, go online with:\n"
                "/doctor_on"
            ),
        )
        await query.edit_message_text(
            f"Doctor approved successfully.\n\n"
            f"Name: {doctor_name}\n"
            f"User ID: {doctor_id}"
        )
        return

    if action == "reject":
        pending_doctors.pop(doctor_id, None)
        await context.bot.send_message(
            chat_id=doctor_id,
            text=(
                "Doctor Verification Rejected\n\n"
                "Your submitted credentials could not be approved at this time.\n\n"
                "You may reapply using:\n"
                "/request_doctor"
            ),
        )
        await query.edit_message_text(
            f"Doctor request rejected.\n\n"
            f"Name: {doctor_name}\n"
            f"User ID: {doctor_id}"
        )
        return

    await query.edit_message_text("Unknown action.")
