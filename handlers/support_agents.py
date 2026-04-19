from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from synmed_utils.admin import is_admin
from synmed_utils.support_registry import (
    approve_support_agent,
    end_support_chat,
    is_in_support_chat,
    is_support_approved,
    pending_support_requests,
    pop_waiting_support_user,
    set_support_available,
    start_support_chat,
    support_profiles,
)


SUPPORT_REQUEST_STATE_KEY = "support_request_state"
SUPPORT_REQUEST_NAME = "support_request_name"
SUPPORT_REQUEST_ROLE = "support_request_role"


async def request_support_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if is_support_approved(update.effective_user.id):
        await update.message.reply_text("You are already an approved support agent.")
        return

    if update.effective_user.id in pending_support_requests:
        await update.message.reply_text("Your support agent request is already under review.")
        return

    context.user_data[SUPPORT_REQUEST_STATE_KEY] = SUPPORT_REQUEST_NAME
    await update.message.reply_text("Support agent application\n\nWhat is your full name?")


async def handle_support_request_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    state = context.user_data.get(SUPPORT_REQUEST_STATE_KEY)
    if not state:
        return

    if state == SUPPORT_REQUEST_NAME:
        context.user_data["support_request_name"] = update.message.text.strip()
        context.user_data[SUPPORT_REQUEST_STATE_KEY] = SUPPORT_REQUEST_ROLE
        await update.message.reply_text("What is your support role or team?")
        return

    if state == SUPPORT_REQUEST_ROLE:
        agent_id = update.effective_user.id
        profile = {
            "name": context.user_data.get("support_request_name", "N/A"),
            "role": update.message.text.strip(),
            "username": update.effective_user.username or "N/A",
        }
        pending_support_requests[agent_id] = profile
        context.user_data.pop(SUPPORT_REQUEST_STATE_KEY, None)
        context.user_data.pop("support_request_name", None)

        await update.message.reply_text("Your support agent request has been submitted for admin approval.")

        keyboard = InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("Approve", callback_data=f"supportapprove:{agent_id}"),
                InlineKeyboardButton("Reject", callback_data=f"supportreject:{agent_id}"),
            ]]
        )
        for admin_id in context.bot_data.get("admin_ids_cache", []):
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=(
                        "New Support Agent Request\n\n"
                        f"Name: {profile['name']}\n"
                        f"Role: {profile['role']}\n"
                        f"Username: @{profile['username']}\n"
                        f"User ID: {agent_id}"
                    ),
                    reply_markup=keyboard,
                )
            except Exception:
                pass


async def support_approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("Admin-only action.")
        return

    action, raw_agent_id = query.data.split(":")
    agent_id = int(raw_agent_id)
    profile = pending_support_requests.get(agent_id)
    if not profile:
        await query.edit_message_text("Support request already processed.")
        return

    if action == "supportapprove":
        approve_support_agent(agent_id, profile)
        pending_support_requests.pop(agent_id, None)
        await context.bot.send_message(
            chat_id=agent_id,
            text="Your support agent request was approved.\nUse /support_on to start receiving customer care chats.",
        )
        await query.edit_message_text(
            f"Support agent approved.\n\nName: {profile['name']}\nRole: {profile['role']}\nUser ID: {agent_id}"
        )
        return

    pending_support_requests.pop(agent_id, None)
    await context.bot.send_message(
        chat_id=agent_id,
        text="Your support agent request was rejected.\nYou can reapply later with /request_support.",
    )
    await query.edit_message_text(
        f"Support agent request rejected.\n\nName: {profile['name']}\nUser ID: {agent_id}"
    )


async def support_on_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    agent_id = update.effective_user.id
    if not is_support_approved(agent_id):
        await update.message.reply_text("You are not an approved support agent.\nUse /request_support first.")
        return

    if is_in_support_chat(agent_id):
        await update.message.reply_text("You are already in an active support session.\nUse /end_support when done.")
        return

    waiting_user = pop_waiting_support_user()
    if waiting_user is None:
        set_support_available(agent_id)
        await update.message.reply_text("You are ONLINE for customer care and waiting for users.")
        return

    start_support_chat(waiting_user, agent_id)
    profile = support_profiles.get(agent_id, {})
    agent_name = profile.get("name", "Support Agent")
    await context.bot.send_message(
        chat_id=waiting_user,
        text=(
            "You are now connected to SynMed Customer Care.\n\n"
            f"Agent: {agent_name}\n"
            "You may begin chatting."
        ),
    )
    await update.message.reply_text(
        f"You are now connected to user {waiting_user}. You may begin chatting."
    )


async def support_off_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    from synmed_utils.support_registry import (
        available_support_agents,
        busy_support_agents,
        remove_support_presence,
    )

    agent_id = update.effective_user.id
    available_support_agents.discard(agent_id)
    busy_support_agents.discard(agent_id)
    remove_support_presence(agent_id)
    await update.message.reply_text("You are now OFFLINE for customer care.")


async def end_support_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user_id = update.effective_user.id
    partner_id = end_support_chat(user_id)
    if partner_id is None:
        await update.message.reply_text("You are not in an active support session.")
        return

    await update.message.reply_text("Customer care session ended.")
    try:
        await context.bot.send_message(chat_id=partner_id, text="Customer care session ended.")
    except Exception:
        pass
