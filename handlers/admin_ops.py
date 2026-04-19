import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from services.admin_audit import log_admin_action
from services.analytics import get_admin_analytics
from services.backups import create_database_backup
from services.consultation_records import get_consultation_timeline
from services.followups import (
    get_due_follow_up_reminders,
    get_upcoming_follow_ups,
    mark_follow_up_reminded,
)
from synmed_utils.admin import is_admin


LOGGER = logging.getLogger(__name__)


def format_analytics_text() -> str:
    metrics = get_admin_analytics()
    busiest = metrics["busiest_doctor"] or "N/A"
    busiest_count = metrics["busiest_doctor_count"]
    return (
        "SynMed Analytics\n\n"
        f"Registered Patients: {metrics['patients']}\n"
        f"Total Consultations: {metrics['consultations']}\n"
        f"Active Consultations: {metrics['active_consultations']}\n"
        f"Closed Consultations: {metrics['closed_consultations']}\n"
        f"Prescriptions Issued: {metrics['prescriptions']}\n"
        f"Investigations Issued: {metrics['investigations']}\n"
        f"Scheduled Follow-ups: {metrics['follow_ups']}\n"
        f"Busiest Doctor: {busiest} ({busiest_count})"
    )


async def analytics_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin-only command.")
        return

    await update.message.reply_text(format_analytics_text())
    log_admin_action(
        admin_id=update.effective_user.id,
        action="view_analytics_dashboard",
        target_type="analytics",
        target_id="summary",
        details="Viewed analytics summary",
    )


async def consultation_timeline_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin-only command.")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /consultation_timeline <consultation_id_or_hospital_number>"
        )
        return

    timeline = get_consultation_timeline(" ".join(context.args))
    if not timeline:
        await update.message.reply_text("Consultation timeline not found.")
        return

    lines = [f"Consultation Timeline: {timeline['consultation_id']}", ""]
    for event in timeline["events"]:
        actor = event["actor_id"] or "system"
        lines.append(
            f"{event['created_at']} | {event['event_type']} | {actor} | {event['details'] or 'N/A'}"
        )
    await update.message.reply_text("\n".join(lines))
    log_admin_action(
        admin_id=update.effective_user.id,
        action="view_consultation_timeline",
        target_type="consultation",
        target_id=timeline["consultation_id"],
        details="Viewed consultation timeline",
    )


async def followups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin-only command.")
        return

    appointments = get_upcoming_follow_ups()
    if not appointments:
        await update.message.reply_text("No scheduled follow-ups.")
        return

    lines = ["Upcoming Follow-ups", ""]
    for appointment in appointments:
        lines.append(
            f"{appointment['scheduled_for']} | Patient {appointment['patient_id']} | Doctor {appointment['doctor_id']}"
        )
    await update.message.reply_text("\n".join(lines))
    log_admin_action(
        admin_id=update.effective_user.id,
        action="view_followups",
        target_type="followups",
        target_id="upcoming",
        details=f"Viewed {len(appointments)} scheduled follow-ups",
    )


async def send_due_followup_reminders(bot, *, lead_hours: int = 24) -> int:
    due = get_due_follow_up_reminders(lead_hours=lead_hours)
    sent = 0
    for item in due:
        if not item["telegram_id"]:
            continue
        try:
            await bot.send_message(
                chat_id=item["telegram_id"],
                text=(
                    "Follow-up Reminder\n\n"
                    f"You have a follow-up appointment scheduled for {item['scheduled_for']}.\n"
                    f"Notes: {item['notes'] or 'No extra notes'}\n"
                    f"Reference: {item['appointment_id'][:8]}\n\n"
                    "Use Book Appointment to choose Pay Now, Pay Later, or I Have Paid Before."
                ),
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Book Appointment", callback_data="book_appointment")]]
                ),
            )
        except Exception as exc:
            LOGGER.warning(
                "Failed to send follow-up reminder for %s: %s",
                item["appointment_id"],
                exc,
            )
            continue
        mark_follow_up_reminded(item["appointment_id"])
        sent += 1
    return sent


async def send_followup_reminders_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin-only command.")
        return

    sent = await send_due_followup_reminders(context.bot)
    if not sent:
        await update.message.reply_text("No follow-up reminders are due right now.")
        return

    await update.message.reply_text(f"Sent {sent} follow-up reminder(s).")
    log_admin_action(
        admin_id=update.effective_user.id,
        action="send_followup_reminders",
        target_type="followups",
        target_id="due",
        details=f"Sent {sent} follow-up reminders",
    )


async def send_followup_reminders_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("Admin-only action.")
        return

    sent = await send_due_followup_reminders(context.bot)
    if not sent:
        await query.edit_message_text("No follow-up reminders are due right now.")
        return

    await query.edit_message_text(f"Sent {sent} follow-up reminder(s).")
    log_admin_action(
        admin_id=query.from_user.id,
        action="send_followup_reminders",
        target_type="followups",
        target_id="due",
        details=f"Sent {sent} follow-up reminders from inline button",
    )


async def backup_database_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("Admin-only action.")
        return

    backup = create_database_backup()
    with open(backup["path"], "rb") as backup_file:
        await context.bot.send_document(
            chat_id=query.from_user.id,
            document=backup_file,
            filename=backup["filename"],
            caption="SynMed database backup",
        )
    await query.edit_message_text("Database backup created and sent.")
    log_admin_action(
        admin_id=query.from_user.id,
        action="backup_database",
        target_type="database",
        target_id=backup["filename"],
        details="Created and downloaded database backup from inline button",
    )
