from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from services.consultation_records import log_consultation_event
from services.followups import schedule_follow_up
from synmed_utils.active_chats import get_last_consultation, is_in_chat
from synmed_utils.verified_doctors import is_verified


FOLLOWUP_STATE_KEY = "followup_state"
FOLLOWUP_DRAFT_KEY = "followup_draft"
FOLLOWUP_DATE_STATE = "followup_date"
FOLLOWUP_TIME_STATE = "followup_time"
FOLLOWUP_NOTES_STATE = "followup_notes"


def _parse_followup_payload(payload: str):
    parts = [part.strip() for part in payload.split("|", 1)]
    scheduled_for = parts[0]
    notes = parts[1] if len(parts) > 1 else ""
    datetime.strptime(scheduled_for, "%Y-%m-%d %H:%M")
    return scheduled_for, notes


def _schedule_for_current_consultation(*, doctor_id: int, context: ContextTypes.DEFAULT_TYPE, scheduled_for: str, notes: str):
    consultation = get_last_consultation(doctor_id)
    if not consultation:
        return None

    patient_details = consultation.get("patient_details", {})
    appointment = schedule_follow_up(
        consultation_id=consultation["consultation_id"],
        patient_id=patient_details.get("hospital_number", str(consultation["patient_id"])),
        doctor_id=doctor_id,
        scheduled_for=scheduled_for,
        notes=notes,
    )
    log_consultation_event(
        consultation["consultation_id"],
        event_type="followup_scheduled",
        actor_id=str(doctor_id),
        details=f"{scheduled_for} | {notes}",
    )
    return appointment, consultation


def _build_date_picker(week_offset: int = 0) -> InlineKeyboardMarkup:
    today = datetime.now().date()
    start_day = today + timedelta(days=week_offset * 7)
    rows = []
    buttons = []
    for offset in range(7):
        day = start_day + timedelta(days=offset)
        label = day.strftime("%a %d %b")
        buttons.append(
            InlineKeyboardButton(label, callback_data=f"followup_date:{day.isoformat()}")
        )
        if len(buttons) == 2:
            rows.append(buttons)
            buttons = []
    if buttons:
        rows.append(buttons)
    navigation = []
    if week_offset > 0:
        navigation.append(
            InlineKeyboardButton("Previous Week", callback_data=f"followup_nav:{week_offset - 1}")
        )
    navigation.append(
        InlineKeyboardButton("Next Week", callback_data=f"followup_nav:{week_offset + 1}")
    )
    rows.append(navigation)
    rows.append([InlineKeyboardButton("Cancel", callback_data="followup_date:cancel")])
    return InlineKeyboardMarkup(rows)


async def followup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    doctor_id = update.effective_user.id
    if not is_verified(doctor_id):
        await update.message.reply_text("Only verified doctors can schedule follow-ups.")
        return

    if not is_in_chat(doctor_id):
        await update.message.reply_text("You need an active consultation to schedule a follow-up.")
        return

    consultation = get_last_consultation(doctor_id)
    if not consultation:
        await update.message.reply_text("Consultation record not found.")
        return

    payload = " ".join(getattr(context, "args", [])).strip()
    if not payload:
        context.user_data[FOLLOWUP_STATE_KEY] = FOLLOWUP_DATE_STATE
        context.user_data[FOLLOWUP_DRAFT_KEY] = {"week_offset": 0}
        await update.message.reply_text(
            "Choose the follow-up date.",
            reply_markup=_build_date_picker(),
        )
        return

    try:
        scheduled_for, notes = _parse_followup_payload(payload)
    except ValueError:
        await update.message.reply_text(
            "Invalid follow-up format.\nUse: /followup <YYYY-MM-DD HH:MM> | <notes>"
        )
        return

    result = _schedule_for_current_consultation(
        doctor_id=doctor_id,
        context=context,
        scheduled_for=scheduled_for,
        notes=notes,
    )
    if not result:
        await update.message.reply_text("Consultation record not found.")
        return
    appointment, consultation = result

    await update.message.reply_text(f"Follow-up scheduled for {scheduled_for}.")
    try:
        await context.bot.send_message(
            chat_id=consultation["patient_id"],
            text=(
                "Your follow-up appointment has been scheduled.\n\n"
                f"When: {scheduled_for}\n"
                f"Notes: {notes or 'No extra notes'}\n"
                f"Reference: {appointment['appointment_id'][:8]}\n\n"
                "Use Book Appointment to confirm payment now or later."
            ),
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Book Appointment", callback_data="book_appointment")]]
            ),
        )
    except Exception:
        pass


async def handle_followup_date_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    doctor_id = query.from_user.id
    if not is_verified(doctor_id):
        await query.edit_message_text("Only verified doctors can schedule follow-ups.")
        return

    state = context.user_data.get(FOLLOWUP_STATE_KEY)
    if state != FOLLOWUP_DATE_STATE:
        await query.edit_message_text("No active follow-up scheduling session was found.")
        return

    if not is_in_chat(doctor_id):
        context.user_data.pop(FOLLOWUP_STATE_KEY, None)
        context.user_data.pop(FOLLOWUP_DRAFT_KEY, None)
        await query.edit_message_text("Active consultation not found. Follow-up scheduling cancelled.")
        return

    selected = query.data.split(":", 1)[1]
    if selected == "cancel":
        context.user_data.pop(FOLLOWUP_STATE_KEY, None)
        context.user_data.pop(FOLLOWUP_DRAFT_KEY, None)
        await query.edit_message_text("Follow-up scheduling cancelled.")
        return

    draft = context.user_data.get(FOLLOWUP_DRAFT_KEY, {})
    context.user_data[FOLLOWUP_DRAFT_KEY] = {
        "selected_date": selected,
        "week_offset": draft.get("week_offset", 0),
    }
    context.user_data[FOLLOWUP_STATE_KEY] = FOLLOWUP_TIME_STATE
    await query.edit_message_text(
        f"Selected date: {selected}\n\nNow enter the time in 24-hour format.\nExample: 14:30"
    )


async def handle_followup_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    doctor_id = query.from_user.id
    if not is_verified(doctor_id):
        await query.edit_message_text("Only verified doctors can schedule follow-ups.")
        return

    state = context.user_data.get(FOLLOWUP_STATE_KEY)
    if state != FOLLOWUP_DATE_STATE:
        await query.edit_message_text("No active follow-up scheduling session was found.")
        return

    if not is_in_chat(doctor_id):
        context.user_data.pop(FOLLOWUP_STATE_KEY, None)
        context.user_data.pop(FOLLOWUP_DRAFT_KEY, None)
        await query.edit_message_text("Active consultation not found. Follow-up scheduling cancelled.")
        return

    week_offset = int(query.data.split(":", 1)[1])
    context.user_data[FOLLOWUP_DRAFT_KEY] = {"week_offset": week_offset}
    await query.edit_message_text(
        "Choose the follow-up date.",
        reply_markup=_build_date_picker(week_offset),
    )


async def handle_followup_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    doctor_id = update.effective_user.id
    if not is_verified(doctor_id):
        return

    state = context.user_data.get(FOLLOWUP_STATE_KEY)
    if not state:
        return

    if not is_in_chat(doctor_id):
        context.user_data.pop(FOLLOWUP_STATE_KEY, None)
        context.user_data.pop(FOLLOWUP_DRAFT_KEY, None)
        await update.message.reply_text("Active consultation not found. Follow-up scheduling cancelled.")
        return

    if state == FOLLOWUP_DATE_STATE:
        await update.message.reply_text(
            "Please choose the follow-up date from the buttons above."
        )
        return

    if state == FOLLOWUP_TIME_STATE:
        draft = context.user_data.get(FOLLOWUP_DRAFT_KEY, {})
        selected_date = draft.get("selected_date")
        if not selected_date:
            context.user_data.pop(FOLLOWUP_STATE_KEY, None)
            context.user_data.pop(FOLLOWUP_DRAFT_KEY, None)
            await update.message.reply_text("Follow-up session expired.")
            return

        entered_time = update.message.text.strip()
        try:
            datetime.strptime(f"{selected_date} {entered_time}", "%Y-%m-%d %H:%M")
        except ValueError:
            await update.message.reply_text(
                "Invalid time format.\nUse HH:MM in 24-hour format, for example 14:30."
            )
            return

        context.user_data[FOLLOWUP_DRAFT_KEY] = {
            "scheduled_for": f"{selected_date} {entered_time}"
        }
        context.user_data[FOLLOWUP_STATE_KEY] = FOLLOWUP_NOTES_STATE
        await update.message.reply_text(
            "Enter follow-up notes, or reply with `skip` if there are no extra notes."
        )
        return

    if state == FOLLOWUP_NOTES_STATE:
        draft = context.user_data.get(FOLLOWUP_DRAFT_KEY, {})
        scheduled_for = draft.get("scheduled_for")
        if not scheduled_for:
            context.user_data.pop(FOLLOWUP_STATE_KEY, None)
            context.user_data.pop(FOLLOWUP_DRAFT_KEY, None)
            await update.message.reply_text("Follow-up session expired.")
            return

        notes = "" if update.message.text.strip().lower() == "skip" else update.message.text.strip()
        result = _schedule_for_current_consultation(
            doctor_id=doctor_id,
            context=context,
            scheduled_for=scheduled_for,
            notes=notes,
        )
        context.user_data.pop(FOLLOWUP_STATE_KEY, None)
        context.user_data.pop(FOLLOWUP_DRAFT_KEY, None)
        if not result:
            await update.message.reply_text("Consultation record not found.")
            return

        appointment, consultation = result
        await update.message.reply_text(f"Follow-up scheduled for {scheduled_for}.")
        try:
            await context.bot.send_message(
                chat_id=consultation["patient_id"],
                text=(
                    "Your follow-up appointment has been scheduled.\n\n"
                    f"When: {scheduled_for}\n"
                    f"Notes: {notes or 'No extra notes'}\n"
                    f"Reference: {appointment['appointment_id'][:8]}\n\n"
                    "Use Book Appointment to confirm payment now or later."
                ),
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Book Appointment", callback_data="book_appointment")]]
                ),
            )
        except Exception:
            pass
