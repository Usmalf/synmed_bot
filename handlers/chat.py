import asyncio
import mimetypes
from pathlib import Path
from uuid import uuid4

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes
from handlers.clinical_documents import LETTER_DRAFT_KEY
from handlers.doctor_notes import PENDING_NOTE_KEY, SKIP_RELAY_ONCE_KEY

from synmed_utils.active_chats import (
    get_last_consultation,
    get_partner,
    is_in_chat,
    restore_runtime_state,
)
from synmed_utils.support_registry import get_support_partner, is_in_support_chat
from services.consultation_records import log_consultation_message


DOCUMENT_DRAFT_KEY = "clinical_document_draft"
ROOT_DIR = Path(__file__).resolve().parent.parent
CONSULTATION_MEDIA_DIR = ROOT_DIR / "consultation_media"


def _message_log_text(message) -> str | None:
    if message.text:
        return message.text
    if message.photo:
        return f"[Photo] {message.caption}".strip()
    if message.video:
        return f"[Video] {message.caption}".strip()
    if message.document:
        filename = message.document.file_name or "document"
        caption = f" {message.caption}" if message.caption else ""
        return f"[Document: {filename}]{caption}"
    return None


def _chat_action_for_message(message) -> str:
    if message.photo:
        return ChatAction.UPLOAD_PHOTO
    if message.video:
        return ChatAction.UPLOAD_VIDEO
    if message.document:
        return ChatAction.UPLOAD_DOCUMENT
    return ChatAction.TYPING


def _media_metadata(message):
    if message.photo:
        return message.photo[-1].file_id, "image/jpeg", ".jpg", message.caption or "[Photo]"
    if message.video:
        suffix = Path(message.video.file_name or "video.mp4").suffix or ".mp4"
        return message.video.file_id, message.video.mime_type or "video/mp4", suffix, message.caption or "[Video]"
    if message.document:
        filename = message.document.file_name or "document"
        suffix = Path(filename).suffix or mimetypes.guess_extension(message.document.mime_type or "") or ".bin"
        label = f"[Document: {filename}]"
        if message.caption:
            label = f"{label} {message.caption}"
        return message.document.file_id, message.document.mime_type or "application/octet-stream", suffix, label
    return None


async def _save_message_media(message, consultation_id: str, context: ContextTypes.DEFAULT_TYPE):
    metadata = _media_metadata(message)
    if not metadata:
        return None, None, None

    file_id, asset_type, suffix, log_text = metadata
    telegram_file = await context.bot.get_file(file_id)
    CONSULTATION_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{consultation_id[:8]}_{uuid4().hex[:10]}{suffix}"
    path = CONSULTATION_MEDIA_DIR / filename
    await telegram_file.download_to_drive(custom_path=str(path))
    return f"consultation_media/{filename}", asset_type, log_text


async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    # Keep clinical document drafting private until the final file is sent.
    if (
        context.user_data.get(DOCUMENT_DRAFT_KEY)
        or context.user_data.get(LETTER_DRAFT_KEY)
        or context.user_data.get(PENDING_NOTE_KEY)
    ):
        return

    if context.user_data.pop(SKIP_RELAY_ONCE_KEY, False):
        return

    sender_id = update.effective_user.id
    restore_runtime_state()

    in_consultation_chat = is_in_chat(sender_id)
    in_support_chat = is_in_support_chat(sender_id)
    if not in_consultation_chat and not in_support_chat:
        return

    receiver_id = get_partner(sender_id) if in_consultation_chat else get_support_partner(sender_id)
    if not receiver_id:
        return

    await context.bot.send_chat_action(
        chat_id=receiver_id,
        action=_chat_action_for_message(update.message),
    )

    await asyncio.sleep(1)

    consultation = get_last_consultation(sender_id)
    if in_consultation_chat and consultation:
        patient_details = consultation.get("patient_details") or {}
        is_web_patient = patient_details.get("source") == "web"
        sender_role = "doctor" if sender_id == consultation.get("doctor_id") else "patient"
        log_text = _message_log_text(update.message)
        asset_path = None
        asset_type = None
        if sender_role == "doctor" and is_web_patient:
            asset_path, asset_type, media_log_text = await _save_message_media(
                update.message,
                consultation["consultation_id"],
                context,
            )
            if media_log_text:
                log_text = media_log_text
        if log_text:
            log_consultation_message(
                consultation["consultation_id"],
                sender_id=sender_id,
                sender_role=sender_role,
                message_text=log_text,
                asset_path=asset_path,
                asset_type=asset_type,
            )
        if is_web_patient and sender_role == "doctor":
            return

    await context.bot.copy_message(
        chat_id=receiver_id,
        from_chat_id=update.effective_chat.id,
        message_id=update.message.message_id,
    )
