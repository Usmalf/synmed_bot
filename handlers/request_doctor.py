import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters
)

from synmed_utils.pending_doctors import pending_doctors
from synmed_utils.doctor_profiles import create_or_update_profile, doctor_profiles
from synmed_utils.verified_doctors import is_verified


# ─────────────────────────────────────
# Conversation states
# ─────────────────────────────────────
NAME, SPECIALTY, EXPERIENCE, LICENSE, CREDENTIAL = range(5)


# ─────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────
async def doctor_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    doctor_id = user.id

    # 🔒 Private chat only
    if update.effective_chat.type != "private":
        await update.message.reply_text(
            "⚠️ Please use this command in a private chat."
        )
        return ConversationHandler.END

    # ✅ BLOCK VERIFIED DOCTORS (FIXED)
    if is_verified(doctor_id):
        await update.message.reply_text(
            "✅ You are already a *verified doctor*.\n\n"
            "There is no need to submit another request.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    # ⚠️ ALSO BLOCK IF PROFILE SAYS VERIFIED
    profile = doctor_profiles.get(doctor_id)
    if profile and profile.get("verified") is True:
        await update.message.reply_text(
            "✅ Your account is already verified.\n\n"
            "You can now receive patient consultations.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    # ⏳ BLOCK DUPLICATE REQUESTS
    if doctor_id in pending_doctors:
        await update.message.reply_text(
            "⏳ Your verification request is already under review.\n"
            "Please wait for admin approval."
        )
        return ConversationHandler.END

    # 🟢 START FLOW
    context.user_data.clear()
    await update.message.reply_text("👨‍⚕️ Full name?")
    return NAME


# ─────────────────────────────────────
# DATA COLLECTION STEPS
# ─────────────────────────────────────
async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("🩺 Specialty?")
    return SPECIALTY


async def get_specialty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["specialty"] = update.message.text.strip()
    await update.message.reply_text("📅 Years of experience?")
    return EXPERIENCE


async def get_experience(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["experience"] = update.message.text.strip()
    await update.message.reply_text("📄 MDCN licence number?")
    return LICENSE


async def get_license(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["license_id"] = update.message.text.strip()
    await update.message.reply_text(
        "📎 Upload your medical license (PDF or image)"
    )
    return CREDENTIAL


# ─────────────────────────────────────
# CREDENTIAL HANDLER
# ─────────────────────────────────────
async def receive_credential(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doctor = update.effective_user
    doctor_id = doctor.id

    # ── SAFETY CHECK ───────────────────
    required_fields = ["name", "specialty", "experience", "license_id"]
    if not all(k in context.user_data for k in required_fields):
        await update.message.reply_text(
            "❌ Incomplete data.\nPlease restart with /request_doctor"
        )
        return ConversationHandler.END

    # ── FILE VALIDATION ────────────────
    if update.message.document:
        if update.message.document.file_size > 5_000_000:
            await update.message.reply_text(
                "❌ File too large.\nPlease upload a file under 5MB."
            )
            return CREDENTIAL

        file_id = update.message.document.file_id
        file_type = "document"

    elif update.message.photo:
        file_id = update.message.photo[-1].file_id
        file_type = "photo"

    else:
        await update.message.reply_text(
            "❌ Invalid file type.\nPlease upload a PDF or image."
        )
        return CREDENTIAL

    # ── STORE PROFILE ──────────────────
    create_or_update_profile(
        doctor_id,
        {
            "name": context.user_data["name"],
            "specialty": context.user_data["specialty"],
            "experience": context.user_data["experience"],
            "license_id": context.user_data["license_id"],
            "license_file_id": file_id,
            "license_file_type": file_type,
            "username": doctor.username,
            "verified": False
        }
    )

    # ── STORE PENDING DOCTOR ────────────
    pending_doctors[doctor_id] = {
        "file_id": file_id,
        "file_type": file_type,
        "name": context.user_data["name"],
        "specialty": context.user_data["specialty"],
        "experience": context.user_data["experience"],
        "license_id": context.user_data["license_id"],
        "username": doctor.username or "N/A"
    }

    await update.message.reply_text(
        "✅ Your request has been submitted.\n"
        "An admin will review your credentials shortly."
    )

    admin_id = int(os.getenv("ADMIN_ID", "0"))
    if not admin_id:
        print("❌ ADMIN_ID not set in environment")
        return ConversationHandler.END

    # ── SEND FILE FIRST ─────────────────
    if file_type == "document":
        await context.bot.send_document(
            chat_id=admin_id,
            document=file_id,
            caption="📄 Doctor credential submitted"
        )
    else:
        await context.bot.send_photo(
            chat_id=admin_id,
            photo=file_id,
            caption="📷 Doctor credential submitted"
        )

    await asyncio.sleep(0.5)

    # ── APPROVAL BUTTONS ────────────────
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve:{doctor_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject:{doctor_id}")
        ]
    ])

    info = pending_doctors[doctor_id]

    await context.bot.send_message(
        chat_id=admin_id,
        text=(
            "🩺 *NEW DOCTOR VERIFICATION REQUEST*\n\n"
            f"Name: {info['name']}\n"
            f"Specialty: {info['specialty']}\n"
            f"Experience: {info['experience']} years\n"
            f"License ID: {info['license_id']}\n"
            f"Username: @{info['username']}\n"
            f"User ID: {doctor_id}"
        ),
        parse_mode="Markdown",
        reply_markup=keyboard
    )

    return ConversationHandler.END


# ─────────────────────────────────────
# HANDLER REGISTRATION
# ─────────────────────────────────────
doctor_request_handler = ConversationHandler(
    entry_points=[
        CommandHandler("doctor_request", doctor_request),
        CommandHandler("request_doctor", doctor_request),
    ],
    states={
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
        SPECIALTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_specialty)],
        EXPERIENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_experience)],
        LICENSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_license)],
        CREDENTIAL: [
            MessageHandler(
                (filters.Document.ALL | filters.PHOTO) & filters.ChatType.PRIVATE,
                receive_credential
            )
        ],
    },
    fallbacks=[]
)
