from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import synmed_utils.doctor_registry as registry
from synmed_utils.active_chats import active_chats
from synmed_utils.admin import is_admin
from synmed_utils.doctor_profiles import create_or_update_profile, doctor_profiles
from synmed_utils.doctor_ratings import get_average_rating, get_total_ratings
from services.admin_audit import get_recent_admin_actions, log_admin_action
from handlers.admin_ops import format_analytics_text
from services.patient_records import get_registered_patient_count
from handlers.admin_patient import (
    ADMIN_PENDING_ACTION_KEY,
    CONSULTATION_EXPORT_ACTION,
    PATIENT_EDIT_DATA_KEY,
    PATIENT_EDIT_IDENTIFIER_ACTION,
    PATIENT_LOOKUP_ACTION,
    PATIENT_SEARCH_ACTION,
)
from synmed_utils.pending_doctors import pending_doctors
from synmed_utils.verified_doctors import (
    get_verified_doctor_ids,
    remove_verified_doctor,
)


def build_admin_dashboard():
    idle_doctors = set(registry.available_doctors)
    busy_doctors = set(active_chats.values())
    online_doctors = idle_doctors | busy_doctors
    patient_count = get_registered_patient_count()
    verified_doctor_ids = get_verified_doctor_ids()

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Pending Doctors", callback_data="admin:pending"),
            InlineKeyboardButton("Verified Doctors", callback_data="admin:verified"),
        ],
        [
            InlineKeyboardButton("Ratings Overview", callback_data="admin:ratings"),
            InlineKeyboardButton("Active Chats", callback_data="admin:chats"),
        ],
        [
            InlineKeyboardButton("Patient Records", callback_data="admin:patient_records"),
            InlineKeyboardButton("Edit Patient", callback_data="admin:edit_patient"),
        ],
        [
            InlineKeyboardButton("Search Records", callback_data="admin:search_records"),
            InlineKeyboardButton("Export Consultation", callback_data="admin:export_consultation"),
        ],
        [
            InlineKeyboardButton("Audit Log", callback_data="admin:audit_log"),
            InlineKeyboardButton("Refresh", callback_data="admin:refresh"),
        ],
        [
            InlineKeyboardButton("Analytics", callback_data="admin:analytics"),
            InlineKeyboardButton("Follow-ups", callback_data="admin:followups"),
        ],
        [
            InlineKeyboardButton("Send Reminders", callback_data="admin_followups:send"),
            InlineKeyboardButton("Backup Database", callback_data="admin_backup:run"),
        ],
        [
            InlineKeyboardButton("Back To Summary", callback_data="admin:refresh"),
        ],
    ])

    text = (
        "*SynMed Admin Dashboard*\n\n"
        f"*Pending Requests:* {len(pending_doctors)}\n"
        f"*Verified Doctors:* {len(verified_doctor_ids)}\n\n"
        f"*Registered Patients:* {patient_count}\n\n"
        f"*Online doctors (total):* {len(online_doctors)}\n"
        f"Idle: {len(idle_doctors)}\n"
        f"Busy: {len(busy_doctors)}\n\n"
        f"*Active consultations:* {len(active_chats) // 2}"
    )
    return text, keyboard


async def admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("Admin-only command.")
        return

    text, keyboard = build_admin_dashboard()
    await update.message.reply_text(
        text,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    log_admin_action(
        admin_id=user.id,
        action="view_admin_dashboard",
        target_type="dashboard",
        target_id="summary",
        details="Opened admin dashboard",
    )


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("Admin-only action.")
        return

    action = query.data

    if action == "admin:pending":
        if not pending_doctors:
            await query.edit_message_text("No pending doctor requests.")
            return

        text = "*Pending Doctor Requests*\n\n"
        for doc_id, info in pending_doctors.items():
            text += (
                f"*{info.get('name', 'Unknown Doctor')}*\n"
                f"ID: `{doc_id}`\n"
                f"Username: @{info.get('username', 'N/A')}\n\n"
            )
        await query.edit_message_text(text, parse_mode="Markdown")
        return

    if action == "admin:verified":
        verified_doctor_ids = sorted(get_verified_doctor_ids())
        if not verified_doctor_ids:
            await query.edit_message_text("No verified doctors.")
            return

        text = "*Verified Doctors*\n\n"
        keyboard = []
        for doc_id in verified_doctor_ids:
            profile = doctor_profiles.get(doc_id, {})
            name = profile.get("name", "Unknown Doctor")
            status = (
                "Online" if doc_id in registry.available_doctors
                else "Busy" if doc_id in active_chats.values()
                else "Offline"
            )
            avg_rating = get_average_rating(doc_id)
            total_reviews = get_total_ratings(doc_id)
            rating_text = (
                f"{avg_rating:.1f} star ({total_reviews} reviews)"
                if total_reviews > 0
                else "No ratings yet"
            )
            text += (
                f"*{name}*\n"
                f"ID: `{doc_id}` - {status}\n"
                f"Rating: {rating_text}\n\n"
            )
            keyboard.append([
                InlineKeyboardButton(
                    "View License",
                    callback_data=f"admin:view_license:{doc_id}",
                ),
                InlineKeyboardButton(
                    "Revoke",
                    callback_data=f"admin:revoke:{doc_id}",
                ),
            ])

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        return

    if action == "admin:ratings":
        verified_doctor_ids = get_verified_doctor_ids()
        if not verified_doctor_ids:
            await query.edit_message_text("No verified doctors.")
            return

        doctors = sorted(
            verified_doctor_ids,
            key=lambda doc_id: get_average_rating(doc_id),
            reverse=True,
        )
        text = "*Doctor Ratings Overview*\n\n"
        for doc_id in doctors:
            profile = doctor_profiles.get(doc_id, {})
            name = profile.get("name", "Unknown Doctor")
            avg = get_average_rating(doc_id)
            total = get_total_ratings(doc_id)
            if total > 0:
                text += f"*Dr. {name}* - {avg:.1f} star ({total})\n"
            else:
                text += f"*Dr. {name}* - No ratings yet\n"
        await query.edit_message_text(text, parse_mode="Markdown")
        return

    if action == "admin:patient_records":
        context.user_data[ADMIN_PENDING_ACTION_KEY] = PATIENT_LOOKUP_ACTION
        await query.edit_message_text(
            "Enter the patient's hospital number or phone number."
        )
        return

    if action == "admin:edit_patient":
        context.user_data[ADMIN_PENDING_ACTION_KEY] = PATIENT_EDIT_IDENTIFIER_ACTION
        context.user_data.pop(PATIENT_EDIT_DATA_KEY, None)
        await query.edit_message_text(
            "Enter the patient's hospital number or phone number to edit the record."
        )
        return

    if action == "admin:export_consultation":
        context.user_data[ADMIN_PENDING_ACTION_KEY] = CONSULTATION_EXPORT_ACTION
        await query.edit_message_text(
            "Enter the consultation ID or patient hospital number to export the latest consultation record."
        )
        return

    if action == "admin:search_records":
        context.user_data[ADMIN_PENDING_ACTION_KEY] = PATIENT_SEARCH_ACTION
        await query.edit_message_text(
            "Enter the patient name, hospital number, or phone number to search."
        )
        return

    if action == "admin:audit_log":
        entries = get_recent_admin_actions()
        if not entries:
            await query.edit_message_text("No admin audit entries yet.")
            return

        lines = ["Recent Admin Audit Log", ""]
        for entry in entries:
            lines.append(
                f"{entry['created_at']} | admin {entry['admin_id']} | "
                f"{entry['action']} | {entry['target_type']}:{entry['target_id']}"
            )
        await query.edit_message_text("\n".join(lines))
        log_admin_action(
            admin_id=query.from_user.id,
            action="view_admin_audit_log",
            target_type="admin_audit",
            target_id=str(query.from_user.id),
            details="Viewed recent admin audit log from dashboard",
        )
        return

    if action == "admin:analytics":
        await query.edit_message_text(format_analytics_text())
        log_admin_action(
            admin_id=query.from_user.id,
            action="view_analytics_dashboard",
            target_type="analytics",
            target_id="summary",
            details="Viewed analytics from admin dashboard",
        )
        return

    if action == "admin:followups":
        await query.edit_message_text(
            "Use /followups to view scheduled follow-up appointments.\n"
            "Use /consultation_timeline <consultation_id_or_hospital_number> to inspect a consultation status timeline.\n"
            "Use /send_followup_reminders to send due reminders.\n"
            "Use /backup_db to download a full database backup."
        )
        log_admin_action(
            admin_id=query.from_user.id,
            action="view_followups_prompt",
            target_type="followups",
            target_id="prompt",
            details="Opened follow-up prompt from dashboard",
        )
        return

    if action.startswith("admin:view_license:"):
        doctor_id = int(action.split(":")[-1])
        info = pending_doctors.get(doctor_id)
        if not info:
            profile = doctor_profiles.get(doctor_id)
            if not profile:
                await query.answer("License not found.", show_alert=True)
                return
            file_id = profile.get("license_file_id")
            file_type = profile.get("license_file_type")
        else:
            file_id = info.get("file_id")
            file_type = info.get("file_type")

        if not file_id:
            await query.answer("License file missing.", show_alert=True)
            return

        if file_type == "document":
            await context.bot.send_document(
                chat_id=query.from_user.id,
                document=file_id,
                caption="Doctor License",
            )
        else:
            await context.bot.send_photo(
                chat_id=query.from_user.id,
                photo=file_id,
                caption="Doctor License",
            )
        log_admin_action(
            admin_id=query.from_user.id,
            action="view_doctor_license",
            target_type="doctor",
            target_id=str(doctor_id),
            details="Viewed doctor license",
        )
        return

    if action.startswith("admin:revoke:"):
        doctor_id = int(action.split(":")[-1])
        remove_verified_doctor(doctor_id)
        registry.available_doctors.discard(doctor_id)
        registry.busy_doctors.discard(doctor_id)

        profile = doctor_profiles.get(doctor_id)
        if profile:
            create_or_update_profile(doctor_id, {"verified": False})

        await context.bot.send_message(
            chat_id=doctor_id,
            text=(
                "*Verification Revoked*\n\n"
                "Your doctor verification has been revoked by admin.\n"
                "You are no longer eligible to receive consultations."
            ),
            parse_mode="Markdown",
        )
        await query.edit_message_text(
            f"Doctor `{doctor_id}` verification revoked.",
            parse_mode="Markdown",
        )
        log_admin_action(
            admin_id=query.from_user.id,
            action="revoke_doctor_verification",
            target_type="doctor",
            target_id=str(doctor_id),
            details="Doctor verification revoked",
        )
        return

    if action == "admin:chats":
        if not active_chats:
            await query.edit_message_text("No active consultations.")
            return

        seen = set()
        lines = ["*Active Consultations*", ""]
        for user_id, partner_id in active_chats.items():
            pair = tuple(sorted((user_id, partner_id)))
            if pair in seen:
                continue
            seen.add(pair)
            lines.append(f"`{pair[0]}` <-> `{pair[1]}`")
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown")
        return

    if action == "admin:refresh":
        text, keyboard = build_admin_dashboard()
        await query.edit_message_text(
            text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        return

    await query.edit_message_text("Unknown admin action.")
