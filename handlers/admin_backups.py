from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from services.admin_audit import log_admin_action
from services.backups import create_database_backup
from synmed_utils.admin import is_admin


async def backup_database_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin-only command.")
        return

    backup = create_database_backup()
    with Path(backup["path"]).open("rb") as backup_file:
        await context.bot.send_document(
            chat_id=update.effective_user.id,
            document=backup_file,
            filename=backup["filename"],
            caption="SynMed database backup",
        )
    log_admin_action(
        admin_id=update.effective_user.id,
        action="backup_database",
        target_type="database",
        target_id=backup["filename"],
        details="Created and downloaded database backup",
    )
