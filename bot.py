import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram.error import NetworkError, TimedOut
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from database import init_db
from handlers.admin_backups import backup_database_handler
from handlers.admin_dashboard import admin_callback, admin_dashboard
from handlers.admin_ops import (
    analytics_handler,
    backup_database_callback_handler,
    consultation_timeline_handler,
    followups_handler,
    send_due_followup_reminders,
    send_followup_reminders_callback_handler,
    send_followup_reminders_handler,
)
from handlers.admin_patient import (
    audit_log_handler,
    edit_patient_handler,
    export_consultation_handler,
    handle_admin_followup,
    patient_record_handler,
    search_records_handler,
)
from handlers.approve_reject_callback import approve_reject_callback
from handlers.chat import relay_message
from handlers.clinical_documents import (
    DOCUMENT_DRAFT_KEY,
    LETTER_DRAFT_KEY,
    cancel_document_flow,
    cancel_letter_flow,
    handle_document_diagnosis,
    handle_document_duration,
    handle_document_investigation_item,
    handle_document_investigation_next,
    handle_document_items,
    handle_document_medication_dose,
    handle_document_medication_name,
    handle_document_medication_next,
    handle_document_medication_route,
    handle_document_notes,
    handle_document_review,
    handle_letter_body,
    handle_letter_diagnosis,
    handle_letter_review,
    handle_letter_target,
    start_medical_report,
    start_investigation,
    start_prescription,
    start_referral,
)
from handlers.customer_care import customer_care_callback, customer_care_handler
from handlers.doctor import doctor_off, doctor_on
from handlers.doctor_help import doctor_help_handler
from handlers.doctor_notes import consultation_note_handler, handle_pending_consultation_note
from handlers.doctor_patient_history import doctor_patient_history_handler
from handlers.end_chat import end_chat_confirm_handler, end_chat_handler
from handlers.followups import (
    FOLLOWUP_STATE_KEY,
    followup_handler,
    handle_followup_date_pick,
    handle_followup_input,
    handle_followup_navigation,
)
from handlers.patient import (
    PATIENT_STATE_KEY,
    handle_appointment_callback,
    handle_appointment_date_callback,
    handle_appointment_navigation,
    handle_appointment_time_callback,
    handle_patient_intake,
    handle_payment_callback,
    start_book_appointment,
    start_consult,
)
from handlers.patient_history import patient_history_handler
from handlers.rate_doctor import handle_review, rate_doctor
from handlers.request_doctor import doctor_request_handler
from handlers.support_agents import (
    SUPPORT_REQUEST_STATE_KEY,
    end_support_handler,
    handle_support_request_input,
    request_support_handler,
    support_approval_callback,
    support_off_handler,
    support_on_handler,
)
from handlers.start import start
from handlers.start import handle_consent_callback
from synmed_utils.active_chats import is_in_chat
from synmed_utils.admin import get_admins, load_admins
from synmed_utils.support_registry import is_in_support_chat
from synmed_utils.states import REVIEW
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
from synmed_utils.verified_doctors import load_verified


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

logging.basicConfig(level=logging.INFO)

FOLLOWUP_REMINDER_INTERVAL_SECONDS = int(
    os.getenv("FOLLOWUP_REMINDER_INTERVAL_SECONDS", "300")
)
HOME_TRIGGER_WORDS = {
    "hi",
    "hello",
    "hey",
    "help",
    "start",
    "menu",
    "consultation",
    "customer care",
    "support",
}


async def error_handler(update, context):
    error = context.error
    if isinstance(error, (TimedOut, NetworkError)):
        logging.warning("Network timeout - Telegram API slow.")
    else:
        logging.error("Unhandled error: %s", repr(error))


async def followup_reminder_loop(application):
    interval = max(60, FOLLOWUP_REMINDER_INTERVAL_SECONDS)
    logging.info(
        "Automatic follow-up reminders enabled. Interval: %s seconds.",
        interval,
    )
    while True:
        try:
            sent = await send_due_followup_reminders(application.bot)
            if sent:
                logging.info("Automatic follow-up reminders sent: %s", sent)
        except asyncio.CancelledError:
            logging.info("Automatic follow-up reminder loop stopped.")
            raise
        except Exception as exc:
            logging.warning("Automatic follow-up reminder loop failed: %s", exc)
        await asyncio.sleep(interval)


async def post_init(application):
    reminder_task = asyncio.create_task(
        followup_reminder_loop(application),
        name="followup-reminder-loop",
    )
    application.bot_data["followup_reminder_task"] = reminder_task


async def post_shutdown(application):
    reminder_task = application.bot_data.pop("followup_reminder_task", None)
    if reminder_task:
        reminder_task.cancel()
        try:
            await reminder_task
        except asyncio.CancelledError:
            pass


async def maybe_show_home_menu(update, context):
    message = getattr(update, "message", None)
    if not message or getattr(update.effective_chat, "type", None) != "private":
        return False

    user_id = update.effective_user.id
    if is_in_chat(user_id) or is_in_support_chat(user_id):
        return False

    prompted_users = context.bot_data.setdefault("home_prompted_users", set())
    text = (message.text or "").strip().lower()
    if user_id not in prompted_users or text in HOME_TRIGGER_WORDS:
        prompted_users.add(user_id)
        await start(update, context)
        return True
    return False


async def route_priority_text_inputs(update, context):
    if context.user_data.get(DOCUMENT_DRAFT_KEY) or context.user_data.get(LETTER_DRAFT_KEY):
        return

    if await handle_pending_consultation_note(update, context):
        return

    if context.user_data.get(FOLLOWUP_STATE_KEY):
        await handle_followup_input(update, context)
        return

    if context.user_data.get(SUPPORT_REQUEST_STATE_KEY):
        await handle_support_request_input(update, context)
        return

    if context.user_data.get(PATIENT_STATE_KEY) is not None:
        await handle_patient_intake(update, context)
        return

    if await maybe_show_home_menu(update, context):
        return


def create_application():
    init_db()
    load_verified()
    load_admins()

    app = (
        ApplicationBuilder()
        .token(os.getenv("BOT_TOKEN"))
        .get_updates_connect_timeout(60)
        .get_updates_read_timeout(60)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.bot_data["admin_ids_cache"] = list(get_admins())

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("customer_care", customer_care_handler))
    app.add_handler(CommandHandler("request_support", request_support_handler))
    app.add_handler(CommandHandler("support_on", support_on_handler))
    app.add_handler(CommandHandler("support_off", support_off_handler))
    app.add_handler(CommandHandler("end_support", end_support_handler))
    app.add_handler(CommandHandler("doctor_on", doctor_on))
    app.add_handler(CommandHandler("doctor_off", doctor_off))
    app.add_handler(CommandHandler("doctor_help", doctor_help_handler))
    app.add_handler(CommandHandler("patient_history", doctor_patient_history_handler))
    app.add_handler(CommandHandler("followup", followup_handler))
    app.add_handler(CommandHandler(["consult_note", "save_note", "save"], consultation_note_handler))
    app.add_handler(CommandHandler("end_chat", end_chat_handler))
    app.add_handler(doctor_request_handler)

    app.add_handler(CallbackQueryHandler(handle_consent_callback, pattern="^consent:"))
    app.add_handler(CallbackQueryHandler(start_consult, pattern="^start_consult$"))
    app.add_handler(CallbackQueryHandler(start_book_appointment, pattern="^book_appointment$"))
    app.add_handler(CallbackQueryHandler(customer_care_handler, pattern="^customer_care$"))
    app.add_handler(CallbackQueryHandler(customer_care_callback, pattern="^(customerfaq|customerhuman):"))
    app.add_handler(CallbackQueryHandler(support_approval_callback, pattern="^(supportapprove|supportreject):"))
    app.add_handler(CallbackQueryHandler(handle_payment_callback, pattern="^payment:"))
    app.add_handler(CallbackQueryHandler(handle_appointment_callback, pattern="^appointment:"))
    app.add_handler(CallbackQueryHandler(handle_appointment_navigation, pattern="^appointment_nav:"))
    app.add_handler(CallbackQueryHandler(handle_appointment_date_callback, pattern="^appointment_date:"))
    app.add_handler(CallbackQueryHandler(handle_appointment_time_callback, pattern="^appointment_time:"))
    app.add_handler(CallbackQueryHandler(handle_followup_navigation, pattern="^followup_nav:"))
    app.add_handler(CallbackQueryHandler(handle_followup_date_pick, pattern="^followup_date:"))
    app.add_handler(CallbackQueryHandler(end_chat_confirm_handler, pattern="^endchat:"))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, route_priority_text_inputs),
        group=1,
    )

    app.add_handler(CommandHandler("admin", admin_dashboard))
    app.add_handler(CommandHandler("patient_record", patient_record_handler))
    app.add_handler(CommandHandler("edit_patient", edit_patient_handler))
    app.add_handler(CommandHandler("export_consultation", export_consultation_handler))
    app.add_handler(CommandHandler("search_records", search_records_handler))
    app.add_handler(CommandHandler("audit_log", audit_log_handler))
    app.add_handler(CommandHandler("analytics", analytics_handler))
    app.add_handler(CommandHandler("consultation_timeline", consultation_timeline_handler))
    app.add_handler(CommandHandler("followups", followups_handler))
    app.add_handler(CommandHandler("backup_db", backup_database_handler))
    app.add_handler(CommandHandler("send_followup_reminders", send_followup_reminders_handler))
    app.add_handler(CommandHandler("my_history", patient_history_handler))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin:"))
    app.add_handler(CallbackQueryHandler(approve_reject_callback, pattern="^(approve|reject):"))
    app.add_handler(CallbackQueryHandler(backup_database_callback_handler, pattern="^admin_backup:run$"))
    app.add_handler(CallbackQueryHandler(send_followup_reminders_callback_handler, pattern="^admin_followups:send$"))
    rating_flow = ConversationHandler(
        entry_points=[CallbackQueryHandler(rate_doctor, pattern="rate:")],
        states={
            REVIEW: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_review)],
        },
        fallbacks=[],
    )
    app.add_handler(rating_flow)

    document_flow = ConversationHandler(
        entry_points=[
            CommandHandler("prescription", start_prescription),
            CommandHandler("investigation", start_investigation),
            CommandHandler(["referral", "referra"], start_referral),
            CommandHandler(["medical_report", "medicalreport"], start_medical_report),
        ],
        states={
            DOC_DIAGNOSIS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_document_diagnosis)],
            DOC_ITEMS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_document_items)],
            DOC_MED_ROUTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_document_medication_route)],
            DOC_MED_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_document_medication_name)],
            DOC_MED_DOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_document_medication_dose)],
            DOC_MED_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_document_duration)],
            DOC_MED_NEXT: [
                CallbackQueryHandler(handle_document_medication_next, pattern="^doc_med:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_document_medication_next),
            ],
            DOC_INVESTIGATION_ITEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_document_investigation_item)],
            DOC_INVESTIGATION_NEXT: [
                CallbackQueryHandler(handle_document_investigation_next, pattern="^doc_inv:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_document_investigation_next),
            ],
            DOC_NOTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_document_notes)],
            DOC_REVIEW: [
                CallbackQueryHandler(handle_document_review, pattern="^doc_review:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_document_review),
            ],
            LETTER_DIAGNOSIS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_letter_diagnosis)],
            LETTER_BODY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_letter_body)],
            LETTER_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_letter_target)],
            LETTER_REVIEW: [
                CallbackQueryHandler(handle_letter_review, pattern="^letter_review:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_letter_review),
            ],
        },
        fallbacks=[
            CommandHandler("cancel_doc", cancel_document_flow),
            CommandHandler("cancel_letter", cancel_letter_flow),
        ],
    )
    app.add_handler(document_flow)

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_followup),
        group=3,
    )

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay_message), group=2)
    app.add_handler(
        MessageHandler(
            (filters.PHOTO | filters.VIDEO | filters.Document.ALL) & ~filters.COMMAND,
            relay_message,
        ),
        group=2,
    )
    app.add_error_handler(error_handler)
    return app


def main():
    app = create_application()
    logging.info("SynMed Bot running...")
    app.run_polling(poll_interval=2)


if __name__ == "__main__":
    main()
