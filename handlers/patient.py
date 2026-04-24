import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import synmed_utils.doctor_registry as registry
from services.emergency import detect_emergency
from services.interaction_state import reset_interactive_state
from services.patient_records import (
    attach_telegram_id,
    get_patient_by_identifier,
    patient_summary,
    register_patient,
    update_patient_record,
)
from services.paystack import (
    PaystackError,
    create_payment_reference,
    redeem_payment_token,
    initialize_transaction,
    mark_payment_status,
    mark_payment_verified,
    verify_transaction,
)
from services.followups import confirm_follow_up_booking, get_follow_up_by_reference, schedule_follow_up
from services.consent import CONSENT_SUMMARY, consent_keyboard, has_patient_consented
from synmed_utils.active_chats import end_chat, is_in_chat, restore_runtime_state, start_chat
from synmed_utils.admin import get_admins
from synmed_utils.doctor_profiles import doctor_profiles, verified_badge
from synmed_utils.doctor_ratings import get_average_rating, get_total_ratings


PATIENT_STATE_KEY = "patient_flow_state"
PATIENT_RECORD_KEY = "patient_record"
PAYMENT_CONTEXT_KEY = "payment_context"
LOOKUP = "lookup"
REG_NAME = "reg_name"
REG_AGE = "reg_age"
REG_GENDER = "reg_gender"
REG_PHONE = "reg_phone"
REG_ADDRESS = "reg_address"
REG_ALLERGY = "reg_allergy"
REG_EMAIL = "reg_email"
RETURN_EMAIL = "return_email"
PAYMENT_PENDING = "payment_pending"
SYMPTOMS = "symptoms"
APPOINTMENT_REFERENCE = "appointment_reference"
APPOINTMENT_EMAIL = "appointment_email"
APPOINTMENT_PAYMENT_CODE = "appointment_payment_code"
APPOINTMENT_CONTEXT_KEY = "appointment_context"
APPOINTMENT_DATE = "appointment_date"
APPOINTMENT_TIME = "appointment_time"

PAYSTACK_CURRENCY = os.getenv("PAYSTACK_CURRENCY", "NGN")
NEW_PATIENT_FEE = int(os.getenv("NEW_PATIENT_FEE_NGN", "5000"))
RETURNING_PATIENT_FEE = int(os.getenv("RETURNING_PATIENT_FEE_NGN", "3000"))
NEW_PATIENT_LABEL = os.getenv(
    "NEW_PATIENT_PAYMENT_LABEL",
    "SynMed Registration + Consultation Fee",
)
RETURNING_PATIENT_LABEL = os.getenv(
    "RETURNING_PATIENT_PAYMENT_LABEL",
    "SynMed Consultation Fee",
)
LAGOS_TZ = timezone(timedelta(hours=1))


def _doctor_notice_text(patient_details: dict) -> str:
    emergency_banner = ""
    if patient_details.get("emergency_flag"):
        emergency_banner = (
            "🚨 EMERGENCY FLAG 🚨\n"
            f"Detected red flags: {patient_details.get('emergency_matches', 'N/A')}\n\n"
        )
    return (
        f"{emergency_banner}New Patient Connected\n\n"
        f"Hospital Number: {patient_details.get('hospital_number', 'N/A')}\n"
        f"Name: {patient_details.get('name', 'N/A')}\n"
        f"Age: {patient_details.get('age', 'N/A')}\n"
        f"Gender: {patient_details.get('gender', 'N/A')}\n"
        f"Phone: {patient_details.get('phone', 'N/A')}\n"
        f"Address: {patient_details.get('address', 'N/A')}\n"
        f"Allergy: {patient_details.get('allergy', 'None recorded')}\n\n"
        "Medical History / Symptoms:\n"
        f"{patient_details.get('history', 'N/A')}\n\n"
        "You may begin consultation."
    )


def _is_valid_email(value: str) -> bool:
    value = value.strip()
    return "@" in value and "." in value.split("@")[-1]


def _payment_keyboard(authorization_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Pay Now", url=authorization_url)],
            [InlineKeyboardButton("I Have Paid", callback_data="payment:verify")],
            [InlineKeyboardButton("Cancel Payment", callback_data="payment:cancel")],
        ]
    )


def _payment_expiry_text() -> str:
    expires_at = datetime.now(LAGOS_TZ) + timedelta(hours=24)
    return expires_at.strftime("%I:%M %p on %d %b %Y").lstrip("0")


def _appointment_keyboard(appointment_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Pay Now", callback_data=f"appointment:pay_now:{appointment_id}")],
            [InlineKeyboardButton("Pay Later", callback_data=f"appointment:pay_later:{appointment_id}")],
            [InlineKeyboardButton("I Have Paid Before", callback_data=f"appointment:paid_before:{appointment_id}")],
        ]
    )


def _build_appointment_date_picker(week_offset: int = 0) -> InlineKeyboardMarkup:
    today = datetime.now(LAGOS_TZ).date()
    start_day = today + timedelta(days=week_offset * 7)
    rows = []
    buttons = []
    for offset in range(7):
        day = start_day + timedelta(days=offset)
        buttons.append(
            InlineKeyboardButton(
                day.strftime("%a %d %b"),
                callback_data=f"appointment_date:{day.isoformat()}",
            )
        )
        if len(buttons) == 2:
            rows.append(buttons)
            buttons = []
    if buttons:
        rows.append(buttons)

    navigation = []
    if week_offset > 0:
        navigation.append(
            InlineKeyboardButton(
                "Previous Week",
                callback_data=f"appointment_nav:{week_offset - 1}",
            )
        )
    navigation.append(
        InlineKeyboardButton(
            "Next Week",
            callback_data=f"appointment_nav:{week_offset + 1}",
        )
    )
    rows.append(navigation)
    rows.append([InlineKeyboardButton("Cancel", callback_data="appointment_date:cancel")])
    return InlineKeyboardMarkup(rows)


def _build_appointment_time_picker(selected_date: str) -> InlineKeyboardMarkup:
    slots = ["09:00", "10:30", "12:00", "14:00", "15:30", "17:00"]
    rows = []
    buttons = []
    for slot in slots:
        buttons.append(
            InlineKeyboardButton(
                slot,
                callback_data=f"appointment_time:{selected_date}|{slot}",
            )
        )
        if len(buttons) == 2:
            rows.append(buttons)
            buttons = []
    if buttons:
        rows.append(buttons)
    rows.append([InlineKeyboardButton("Back", callback_data="appointment_time:back")])
    return InlineKeyboardMarkup(rows)


def _clear_registration_context(context: ContextTypes.DEFAULT_TYPE):
    for key in (
        "reg_name",
        "reg_age",
        "reg_gender",
        "reg_phone",
        "reg_address",
        "reg_allergy",
        "reg_email",
    ):
        context.user_data.pop(key, None)


def _clear_payment_context(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop(PAYMENT_CONTEXT_KEY, None)


def _clear_appointment_context(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop(APPOINTMENT_CONTEXT_KEY, None)


async def start_consult(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    reset_interactive_state(context.user_data)
    if not has_patient_consented(query.from_user.id):
        await query.message.reply_text(
            CONSENT_SUMMARY,
            reply_markup=consent_keyboard(),
        )
        return
    restore_runtime_state()
    if is_in_chat(query.from_user.id):
        end_chat(query.from_user.id)
    context.user_data[PATIENT_STATE_KEY] = LOOKUP
    _clear_payment_context(context)
    await query.message.reply_text(
        "Reply with your hospital number or phone number to continue.\n"
        "If this is your first visit, reply with `new`.\n\n"
        "New patient? Pay NGN 5,000 total.\n"
        "This covers NGN 2,000 for registration and NGN 3,000 for consultation."
    )


async def start_book_appointment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    reset_interactive_state(context.user_data)
    if not has_patient_consented(query.from_user.id):
        await query.message.reply_text(
            CONSENT_SUMMARY,
            reply_markup=consent_keyboard(),
        )
        return
    restore_runtime_state()
    if is_in_chat(query.from_user.id):
        end_chat(query.from_user.id)
    context.user_data[PATIENT_STATE_KEY] = APPOINTMENT_REFERENCE
    _clear_payment_context(context)
    _clear_appointment_context(context)
    await query.message.reply_text(
        "Reply with your appointment reference if you already have one.\n"
        "If you are already registered, reply with your hospital number or phone number.\n"
        "If this is your first booking, reply with `new`."
    )


async def handle_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    payment_context = context.user_data.get(PAYMENT_CONTEXT_KEY)
    if not payment_context:
        await query.edit_message_text("No pending payment was found. Please start again with /start.")
        return

    action = query.data.split(":", 1)[1]
    if action == "cancel":
        reference = payment_context.get("reference")
        if reference:
            mark_payment_status(reference, status="cancelled", paystack_status="cancelled")
        context.user_data[PATIENT_STATE_KEY] = LOOKUP
        _clear_payment_context(context)
        _clear_registration_context(context)
        context.user_data.pop(PATIENT_RECORD_KEY, None)
        await query.edit_message_text(
            "Payment cancelled.\nReply with your hospital number or phone number to try again, or reply `new` to register."
        )
        return

    await query.edit_message_text("Checking your payment with Paystack...")
    try:
        verification = await verify_transaction(payment_context["reference"])
    except PaystackError as exc:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"Unable to verify payment right now: {exc}",
        )
        return
    except Exception:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Unable to verify payment right now. Please tap `I Have Paid` again shortly.",
        )
        return

    paystack_status = (verification.get("status") or "").lower()
    amount_ngn = int(verification.get("amount", 0)) // 100
    currency = verification.get("currency")
    if paystack_status != "success":
        mark_payment_status(
            payment_context["reference"],
            status="pending_verification",
            paystack_status=paystack_status or "pending",
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=(
                "Payment is not confirmed yet.\n"
                "After completing payment, come back and tap `I Have Paid` to continue."
            ),
            reply_markup=_payment_keyboard(payment_context["authorization_url"]),
        )
        return

    if amount_ngn != payment_context["amount"] or currency != payment_context["currency"]:
        mark_payment_status(
            payment_context["reference"],
            status="amount_mismatch",
            paystack_status=paystack_status,
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Payment was received but did not match the expected amount or currency. Please contact admin.",
        )
        return

    patient_type = payment_context["patient_type"]
    if patient_type == "new":
        patient = register_patient(
            telegram_id=query.from_user.id,
            name=context.user_data.get("reg_name", "N/A"),
            age=context.user_data.get("reg_age", "0"),
            gender=context.user_data.get("reg_gender", "N/A"),
            phone=context.user_data.get("reg_phone", "N/A"),
            email=context.user_data.get("reg_email", ""),
            address=context.user_data.get("reg_address", "N/A"),
            allergy=context.user_data.get("reg_allergy", ""),
        )
        context.user_data[PATIENT_RECORD_KEY] = patient
        payment_token = mark_payment_verified(
            payment_context["reference"],
            paystack_status=paystack_status,
            patient_id=patient["hospital_number"],
        )
        if payment_context.get("purpose") == "appointment":
            appointment = confirm_follow_up_booking(
                appointment_id=payment_context["appointment_id"],
                payment_status="paid",
                payment_reference=payment_context["reference"],
                payment_token=payment_token,
            )
            _clear_registration_context(context)
            context.user_data.pop(PATIENT_STATE_KEY, None)
            context.user_data.pop(PATIENT_RECORD_KEY, None)
            _clear_payment_context(context)
            _clear_appointment_context(context)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=(
                    "Appointment booked successfully.\n\n"
                    f"When: {appointment['scheduled_for']}\n"
                    f"Payment status: paid\n"
                    f"Payment code: {payment_token}\n\n"
                    f"Keep this code safe. It is valid until {_payment_expiry_text()} for this patient."
                ),
            )
            return
        _clear_registration_context(context)
        context.user_data[PATIENT_STATE_KEY] = SYMPTOMS
        _clear_payment_context(context)
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=(
                "Payment confirmed.\n\n"
                f"Registration completed. Your hospital number is {patient['hospital_number']}.\n"
                f"Payment code: {payment_token}\n"
                f"Please keep it safe. It is valid until {_payment_expiry_text()} for this patient.\n\n"
                "Now describe your medical history / symptoms."
            ),
        )
        return

    patient = context.user_data.get(PATIENT_RECORD_KEY)
    if not patient:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Patient record missing. Please restart with /start.",
        )
        return

    if payment_context["email"] and payment_context["email"] != (patient.get("email") or ""):
        patient = update_patient_record(patient["hospital_number"], "email", payment_context["email"])
        context.user_data[PATIENT_RECORD_KEY] = patient

    payment_token = mark_payment_verified(
        payment_context["reference"],
        paystack_status=paystack_status,
        patient_id=patient["hospital_number"],
    )
    if payment_context.get("purpose") == "appointment":
        appointment = confirm_follow_up_booking(
            appointment_id=payment_context["appointment_id"],
            payment_status="paid",
            payment_reference=payment_context["reference"],
            payment_token=payment_token,
        )
        context.user_data.pop(PATIENT_STATE_KEY, None)
        context.user_data.pop(PATIENT_RECORD_KEY, None)
        _clear_payment_context(context)
        _clear_appointment_context(context)
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=(
                "Appointment booked successfully.\n\n"
                f"When: {appointment['scheduled_for']}\n"
                f"Payment status: paid\n"
                f"Payment code: {payment_token}\n\n"
                f"Keep this code safe. It is valid until {_payment_expiry_text()} for this patient."
            ),
        )
        return
    context.user_data[PATIENT_STATE_KEY] = SYMPTOMS
    _clear_payment_context(context)
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=(
            "Payment confirmed.\n\n"
            f"Payment code: {payment_token}\n"
            f"This code is valid until {_payment_expiry_text()} for this patient.\n"
            "Now describe your medical history / symptoms."
        ),
    )


async def handle_appointment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    if len(parts) != 3:
        await query.edit_message_text("Appointment action could not be understood.")
        return

    action, appointment_id = parts[1], parts[2]
    appointment = get_follow_up_by_reference(appointment_id)
    if not appointment:
        await query.edit_message_text("Appointment reference could not be found.")
        return

    patient = get_patient_by_identifier(appointment["patient_id"])
    if not patient:
        await query.edit_message_text("Patient record linked to this appointment could not be found.")
        return

    if patient.get("telegram_id") in (None, query.from_user.id):
        if patient.get("telegram_id") is None:
            attach_telegram_id(patient["id"], query.from_user.id)
            patient = get_patient_by_identifier(patient["hospital_number"])
    else:
        await query.edit_message_text("This appointment belongs to another patient account.")
        return

    context.user_data[PATIENT_RECORD_KEY] = patient
    context.user_data[APPOINTMENT_CONTEXT_KEY] = dict(appointment)

    if action == "pay_later":
        confirm_follow_up_booking(
            appointment_id=appointment["appointment_id"],
            payment_status="pay_later",
        )
        context.user_data.pop(PATIENT_STATE_KEY, None)
        _clear_payment_context(context)
        _clear_appointment_context(context)
        await query.edit_message_text(
            "Appointment booked successfully.\n\n"
            f"When: {appointment['scheduled_for']}\n"
            "Payment status: pay later.\n\n"
            "You can come back with your appointment reference to complete payment later."
        )
        return

    if action == "paid_before":
        context.user_data[PATIENT_STATE_KEY] = APPOINTMENT_PAYMENT_CODE
        await query.edit_message_text(
            "Reply with your payment code so we can apply it to this appointment."
        )
        return

    if not patient.get("email"):
        context.user_data[PATIENT_STATE_KEY] = APPOINTMENT_EMAIL
        await query.edit_message_text(
            "No email is saved on this patient record.\n"
            "Reply with the email you want to use for appointment payment."
        )
        return

    await query.edit_message_text("Starting appointment payment...")
    await _start_payment(
        query,
        context,
        patient_type="returning",
        email=patient["email"],
        amount=RETURNING_PATIENT_FEE,
        label="SynMed Appointment Booking Fee",
        purpose="appointment",
        appointment_id=appointment["appointment_id"],
    )


async def handle_appointment_date_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    state = context.user_data.get(PATIENT_STATE_KEY)
    if state != APPOINTMENT_DATE:
        await query.edit_message_text("No active appointment booking session was found.")
        return

    selected = query.data.split(":", 1)[1]
    if selected == "cancel":
        context.user_data.pop(PATIENT_STATE_KEY, None)
        _clear_appointment_context(context)
        context.user_data.pop(PATIENT_RECORD_KEY, None)
        await query.edit_message_text("Appointment booking cancelled.")
        return

    appointment_context = context.user_data.get(APPOINTMENT_CONTEXT_KEY) or {}
    appointment_context["scheduled_date"] = selected
    context.user_data[APPOINTMENT_CONTEXT_KEY] = appointment_context
    context.user_data[PATIENT_STATE_KEY] = APPOINTMENT_TIME
    await query.edit_message_text(
        f"Selected date: {selected}\n\nChoose your preferred time slot.",
        reply_markup=_build_appointment_time_picker(selected),
    )


async def handle_appointment_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    state = context.user_data.get(PATIENT_STATE_KEY)
    if state != APPOINTMENT_DATE:
        await query.edit_message_text("No active appointment booking session was found.")
        return

    week_offset = int(query.data.split(":", 1)[1])
    appointment_context = context.user_data.get(APPOINTMENT_CONTEXT_KEY) or {}
    appointment_context["week_offset"] = week_offset
    context.user_data[APPOINTMENT_CONTEXT_KEY] = appointment_context
    await query.edit_message_text(
        "Choose your preferred appointment date.",
        reply_markup=_build_appointment_date_picker(week_offset),
    )


async def handle_appointment_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    state = context.user_data.get(PATIENT_STATE_KEY)
    if state != APPOINTMENT_TIME:
        await query.edit_message_text("No active appointment booking session was found.")
        return

    payload = query.data.split(":", 1)[1]
    if payload == "back":
        appointment_context = context.user_data.get(APPOINTMENT_CONTEXT_KEY) or {}
        context.user_data[PATIENT_STATE_KEY] = APPOINTMENT_DATE
        await query.edit_message_text(
            "Choose your preferred appointment date.",
            reply_markup=_build_appointment_date_picker(appointment_context.get("week_offset", 0)),
        )
        return

    patient = context.user_data.get(PATIENT_RECORD_KEY)
    appointment_context = context.user_data.get(APPOINTMENT_CONTEXT_KEY) or {}
    if not patient:
        await query.edit_message_text("Appointment session expired. Please start again.")
        return

    selected_date, selected_time = payload.split("|", 1)
    scheduled_for = datetime.strptime(
        f"{selected_date} {selected_time}",
        "%Y-%m-%d %H:%M",
    ).strftime("%Y-%m-%d %H:%M")
    appointment = schedule_follow_up(
        consultation_id=f"self-booked-{uuid4().hex[:12]}",
        patient_id=patient["hospital_number"],
        doctor_id=0,
        scheduled_for=scheduled_for,
        notes="Self-booked appointment",
    )
    context.user_data[APPOINTMENT_CONTEXT_KEY] = dict(appointment)
    context.user_data.pop(PATIENT_STATE_KEY, None)
    await query.edit_message_text(
        (
            "Appointment created successfully.\n\n"
            f"Reference: {appointment['appointment_id'][:8]}\n"
            f"When: {appointment['scheduled_for']}\n\n"
            "Choose how you want to handle payment for this appointment."
        ),
        reply_markup=_appointment_keyboard(appointment["appointment_id"]),
    )


async def handle_patient_intake(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    state = context.user_data.get(PATIENT_STATE_KEY)
    if state is None:
        return

    text = update.message.text.strip()

    if state == LOOKUP:
        await _handle_lookup(update, context, text)
        return

    if state == APPOINTMENT_REFERENCE:
        await _handle_appointment_reference(update, context, text)
        return

    if state == APPOINTMENT_EMAIL:
        if not _is_valid_email(text):
            await update.message.reply_text("Please enter a valid email address.")
            return
        appointment = context.user_data.get(APPOINTMENT_CONTEXT_KEY)
        patient = context.user_data.get(PATIENT_RECORD_KEY)
        if not appointment or not patient:
            await update.message.reply_text("Appointment session expired. Please start again.")
            return
        patient = update_patient_record(patient["hospital_number"], "email", text)
        context.user_data[PATIENT_RECORD_KEY] = patient
        await _start_payment(
            update,
            context,
            patient_type="returning",
            email=text,
            amount=RETURNING_PATIENT_FEE,
            label="SynMed Appointment Booking Fee",
            purpose="appointment",
            appointment_id=appointment["appointment_id"],
        )
        return

    if state == APPOINTMENT_PAYMENT_CODE:
        appointment = context.user_data.get(APPOINTMENT_CONTEXT_KEY)
        patient = context.user_data.get(PATIENT_RECORD_KEY)
        if not appointment or not patient:
            await update.message.reply_text("Appointment session expired. Please start again.")
            return
        redeemed = redeem_payment_token(
            payment_token=text,
            patient_id=patient["hospital_number"],
        )
        if not redeemed:
            await update.message.reply_text(
                "That payment code is invalid, already used, or does not belong to this patient."
            )
            return
        confirm_follow_up_booking(
            appointment_id=appointment["appointment_id"],
            payment_status="paid",
            payment_reference=redeemed["reference"],
            payment_token=redeemed["payment_token"],
        )
        context.user_data.pop(PATIENT_STATE_KEY, None)
        context.user_data.pop(PATIENT_RECORD_KEY, None)
        _clear_payment_context(context)
        _clear_appointment_context(context)
        await update.message.reply_text(
            "Appointment booked successfully.\n\n"
            f"When: {appointment['scheduled_for']}\n"
            f"Payment code accepted: {redeemed['payment_token']}\n"
            "Payment status: paid."
        )
        return

    if state == REG_NAME:
        context.user_data["reg_name"] = text
        context.user_data[PATIENT_STATE_KEY] = REG_AGE
        await update.message.reply_text("Age?")
        return

    if state == REG_AGE:
        context.user_data["reg_age"] = text
        context.user_data[PATIENT_STATE_KEY] = REG_GENDER
        await update.message.reply_text("Gender?")
        return

    if state == REG_GENDER:
        context.user_data["reg_gender"] = text
        context.user_data[PATIENT_STATE_KEY] = REG_PHONE
        await update.message.reply_text("Phone number?")
        return

    if state == REG_PHONE:
        context.user_data["reg_phone"] = text
        context.user_data[PATIENT_STATE_KEY] = REG_ADDRESS
        await update.message.reply_text("Home address?")
        return

    if state == REG_ADDRESS:
        context.user_data["reg_address"] = text
        context.user_data[PATIENT_STATE_KEY] = REG_ALLERGY
        await update.message.reply_text("Any allergy? If none, reply with `none`.")
        return

    if state == REG_ALLERGY:
        context.user_data["reg_allergy"] = "" if text.lower() == "none" else text
        context.user_data[PATIENT_STATE_KEY] = REG_EMAIL
        await update.message.reply_text("Enter your real email address for payment verification.")
        return

    if state == REG_EMAIL:
        if not _is_valid_email(text):
            await update.message.reply_text("Please enter a valid email address.")
            return
        context.user_data["reg_email"] = text
        appointment_context = context.user_data.get(APPOINTMENT_CONTEXT_KEY) or {}
        if appointment_context.get("booking_mode") == "new":
            patient = register_patient(
                telegram_id=update.effective_user.id,
                name=context.user_data.get("reg_name", "N/A"),
                age=context.user_data.get("reg_age", "0"),
                gender=context.user_data.get("reg_gender", "N/A"),
                phone=context.user_data.get("reg_phone", "N/A"),
                email=text,
                address=context.user_data.get("reg_address", "N/A"),
                allergy=context.user_data.get("reg_allergy", ""),
            )
            context.user_data[PATIENT_RECORD_KEY] = patient
            _clear_registration_context(context)
            context.user_data[PATIENT_STATE_KEY] = APPOINTMENT_DATE
            await update.message.reply_text(
                "Registration completed.\n\n"
                f"Your hospital number is {patient['hospital_number']}.\n"
                "Now choose your preferred appointment date.",
                reply_markup=_build_appointment_date_picker(),
            )
            return
        await _start_payment(
            update,
            context,
            patient_type="new",
            email=text,
            amount=NEW_PATIENT_FEE,
            label=NEW_PATIENT_LABEL,
        )
        return

    if state == RETURN_EMAIL:
        patient = context.user_data.get(PATIENT_RECORD_KEY)
        normalized_text = text.strip()
        redeemed = redeem_payment_token(
            payment_token=normalized_text,
            patient_id=patient["hospital_number"],
        ) if patient else None
        if redeemed:
            context.user_data[PATIENT_STATE_KEY] = SYMPTOMS
            _clear_payment_context(context)
            verified_at = datetime.fromisoformat(redeemed["verified_at"])
            if verified_at.tzinfo is None:
                verified_at = verified_at.replace(tzinfo=timezone.utc)
            expires_at = verified_at.astimezone(LAGOS_TZ) + timedelta(hours=24)
            await update.message.reply_text(
                "Payment code accepted.\n\n"
                f"Your previous payment is valid until {expires_at.strftime('%I:%M %p on %d %b %Y').lstrip('0')}.\n"
                "Now describe your medical history / symptoms so we can reconnect you."
            )
            return

        looks_like_payment_code = "-" in normalized_text and len(normalized_text) >= 6
        if looks_like_payment_code:
            await update.message.reply_text(
                "That payment code could not be applied to this patient.\n"
                "Please check the code and try again, or enter your email address to pay now."
            )
            return

        if not _is_valid_email(normalized_text):
            await update.message.reply_text(
                "Enter a valid email address to pay now, or enter a valid payment code from a payment made within the last 24 hours."
            )
            return
        await _start_payment(
            update,
            context,
            patient_type="returning",
            email=normalized_text,
            amount=RETURNING_PATIENT_FEE,
            label=RETURNING_PATIENT_LABEL,
        )
        return

    if state == PAYMENT_PENDING:
        await update.message.reply_text(
            "Complete your payment first, then come back and tap `I Have Paid` to continue.",
        )
        return

    if state == SYMPTOMS:
        await _complete_consultation_request(update, context, text)


async def _start_payment(
    update_or_query,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    patient_type: str,
    email: str,
    amount: int,
    label: str,
    purpose: str = "consultation",
    appointment_id: str | None = None,
):
    message = getattr(update_or_query, "message", None)
    effective_user = getattr(update_or_query, "effective_user", None)
    if message is None and getattr(update_or_query, "from_user", None) is not None:
        message = update_or_query.message
        effective_user = update_or_query.from_user

    patient = context.user_data.get(PATIENT_RECORD_KEY)
    reference = create_payment_reference()
    try:
        payment = await initialize_transaction(
            email=email,
            amount_ngn=amount,
            currency=PAYSTACK_CURRENCY,
            reference=reference,
            label=label,
            metadata={
                "telegram_id": effective_user.id,
                "patient_type": patient_type,
                "source": "telegram_bot",
                "patient_id": patient["hospital_number"] if patient else "",
            },
        )
    except PaystackError as exc:
        await message.reply_text(f"Unable to start payment: {exc}")
        return
    except Exception:
        await message.reply_text("Unable to start payment right now. Please try again shortly.")
        return

    context.user_data[PAYMENT_CONTEXT_KEY] = {
        "reference": reference,
        "authorization_url": payment["authorization_url"],
        "amount": amount,
        "currency": PAYSTACK_CURRENCY,
        "patient_type": patient_type,
        "label": label,
        "email": email,
        "purpose": purpose,
        "appointment_id": appointment_id,
    }
    context.user_data[PATIENT_STATE_KEY] = PAYMENT_PENDING
    await message.reply_text(
        (
            f"{label}\n\n"
            f"Amount: NGN {amount:,}\n"
            f"Email: {email}\n\n"
            "Tap `Pay Now` to complete payment.\n"
            "After successful payment, come back here and tap `I Have Paid` to continue."
        ),
        reply_markup=_payment_keyboard(payment["authorization_url"]),
    )


async def _handle_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE, identifier: str):
    if identifier.lower() == "new":
        context.user_data[PATIENT_STATE_KEY] = REG_NAME
        await update.message.reply_text("What is your full name?")
        return

    patient = get_patient_by_identifier(identifier)
    if not patient:
        await update.message.reply_text(
            "Patient record not found.\n"
            "Reply with your hospital number or phone number again, or reply `new` to register.\n\n"
            "New patient fee: NGN 5,000 total.\n"
            "This covers NGN 2,000 for registration and NGN 3,000 for consultation."
        )
        return

    if patient.get("telegram_id") in (None, update.effective_user.id):
        if patient.get("telegram_id") is None:
            attach_telegram_id(patient["id"], update.effective_user.id)
            patient = get_patient_by_identifier(patient["hospital_number"])

        context.user_data[PATIENT_RECORD_KEY] = patient
        context.user_data[PATIENT_STATE_KEY] = RETURN_EMAIL
        await update.message.reply_text(
            "Patient record found.\n\n"
            f"{patient_summary(patient)}\n\n"
            f"Consultation fee: NGN {RETURNING_PATIENT_FEE:,}\n"
            "New patient note: NGN 5,000 total = NGN 2,000 registration + NGN 3,000 consultation.\n"
            "Enter your real email address to continue to payment,\n"
            "or enter a payment code from a payment made within the last 24 hours."
        )
        return

    await update.message.reply_text(
        "This patient record is already linked to another Telegram account.\n"
        "Please contact admin for support."
    )


async def _handle_appointment_reference(update: Update, context: ContextTypes.DEFAULT_TYPE, reference: str):
    if reference.strip().lower() == "new":
        context.user_data[APPOINTMENT_CONTEXT_KEY] = {"booking_mode": "new"}
        context.user_data[PATIENT_STATE_KEY] = REG_NAME
        await update.message.reply_text("What is your full name?")
        return

    existing_patient = get_patient_by_identifier(reference)
    if existing_patient:
        if existing_patient.get("telegram_id") in (None, update.effective_user.id):
            if existing_patient.get("telegram_id") is None:
                attach_telegram_id(existing_patient["id"], update.effective_user.id)
                existing_patient = get_patient_by_identifier(existing_patient["hospital_number"])
        else:
            await update.message.reply_text(
                "This patient record is already linked to another Telegram account."
            )
            return

        context.user_data[PATIENT_RECORD_KEY] = existing_patient
        context.user_data[APPOINTMENT_CONTEXT_KEY] = {"booking_mode": "registered"}
        context.user_data[PATIENT_STATE_KEY] = APPOINTMENT_DATE
        await update.message.reply_text(
            (
                "Registered patient record found.\n\n"
                f"{patient_summary(existing_patient)}\n\n"
                "Now choose your preferred appointment date."
            ),
            reply_markup=_build_appointment_date_picker(),
        )
        return

    appointment = get_follow_up_by_reference(reference)
    if not appointment:
        await update.message.reply_text(
            "Appointment reference not found.\n"
            "Please check the reference and try again."
        )
        return

    patient = get_patient_by_identifier(appointment["patient_id"])
    if not patient:
        await update.message.reply_text("Patient record linked to this appointment could not be found.")
        return

    if patient.get("telegram_id") in (None, update.effective_user.id):
        if patient.get("telegram_id") is None:
            attach_telegram_id(patient["id"], update.effective_user.id)
            patient = get_patient_by_identifier(patient["hospital_number"])
    else:
        await update.message.reply_text(
            "This appointment belongs to another patient account."
        )
        return

    context.user_data[PATIENT_RECORD_KEY] = patient
    context.user_data[APPOINTMENT_CONTEXT_KEY] = dict(appointment)
    context.user_data.pop(PATIENT_STATE_KEY, None)
    await update.message.reply_text(
        (
            "Appointment found.\n\n"
            f"Reference: {appointment['appointment_id'][:8]}\n"
            f"When: {appointment['scheduled_for']}\n"
            f"Notes: {appointment['notes'] or 'No extra notes'}\n"
            f"Current payment status: {appointment['payment_status'] or 'unpaid'}\n\n"
            "Choose how you want to handle payment for this appointment."
        ),
        reply_markup=_appointment_keyboard(appointment["appointment_id"]),
    )


async def _complete_consultation_request(update: Update, context: ContextTypes.DEFAULT_TYPE, symptoms: str):
    patient = context.user_data.get(PATIENT_RECORD_KEY)
    if not patient:
        await update.message.reply_text("Patient record missing. Please restart consultation.")
        return

    patient_id = update.effective_user.id
    emergency = detect_emergency(symptoms)
    patient_details = {
        "hospital_number": patient["hospital_number"],
        "name": patient["name"],
        "age": str(patient["age"]),
        "gender": patient["gender"],
        "phone": patient["phone"],
        "address": patient.get("address") or "N/A",
        "allergy": patient.get("allergy") or "None recorded",
        "history": symptoms,
        "telegram_id": patient.get("telegram_id") or patient_id,
        "emergency_flag": emergency["is_emergency"],
        "emergency_matches": ", ".join(emergency["matches"]) if emergency["matches"] else "",
    }

    if emergency["is_emergency"]:
        await update.message.reply_text(
            "🚨 Emergency Alert 🚨\n\n"
            "Your symptoms suggest this may be an urgent or life-threatening condition.\n"
            "🚩 Please seek immediate in-person emergency care or call your local emergency number right away.\n"
            "We will still alert the available medical team on SynMed."
        )
        for admin_id in get_admins():
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=(
                        "🚨 Emergency case flagged 🚨\n\n"
                        f"Patient: {patient['hospital_number']} - {patient['name']}\n"
                        f"Triggers: {patient_details['emergency_matches']}\n"
                        f"Symptoms: {symptoms}"
                    ),
                )
            except Exception:
                pass

    if registry.available_doctors:
        doctor_id = registry.available_doctors.pop()
        start_chat(patient_id, doctor_id, patient_details)
        registry.set_doctor_busy(doctor_id)

        profile = doctor_profiles.get(doctor_id, {})
        doctor_name = profile.get("name", "Doctor")
        specialty = profile.get("specialty", "N/A")
        experience = profile.get("experience", "N/A")

        avg_rating = get_average_rating(doctor_id)
        total_reviews = get_total_ratings(doctor_id)
        rating_text = (
            f"{avg_rating:.1f} star ({total_reviews} reviews)"
            if total_reviews > 0
            else "No ratings yet"
        )

        await context.bot.send_message(
            chat_id=patient_id,
            text=(
                ("🚨 Emergency case flagged 🚨\n\n" if emergency["is_emergency"] else "")
                + "You are now connected to:\n\n"
                f"Dr. {doctor_name}{verified_badge(doctor_id)}\n"
                f"- Specialty: {specialty}\n"
                f"- Experience: {experience} years\n"
                f"- Rating: {rating_text}\n\n"
                f"Hospital Number: {patient['hospital_number']}\n"
                "You may begin chatting."
            ),
        )

        await context.bot.send_message(
            chat_id=doctor_id,
            text=_doctor_notice_text(patient_details),
        )
    else:
        registry.queue_patient(patient_id, patient_details)
        await update.message.reply_text(
            "No doctor is online. You will be connected shortly."
            if not emergency["is_emergency"]
            else "No doctor is online right now. Please seek emergency in-person care immediately while we keep your case queued for urgent review."
        )

    for key in (
        PATIENT_STATE_KEY,
        PATIENT_RECORD_KEY,
    ):
        context.user_data.pop(key, None)
    _clear_registration_context(context)
    _clear_payment_context(context)
