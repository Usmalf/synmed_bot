from services.runtime_state import (
    load_support_chats,
    load_support_presence,
    load_support_queue,
    remove_support_chat_by_user,
    remove_support_presence,
    remove_support_queue_user,
    save_support_chat,
    save_support_presence,
    save_support_queue_user,
)

approved_support_agents = set()
available_support_agents = set()
busy_support_agents = set()
waiting_support_users = []
pending_support_requests = {}
support_profiles = {}
support_chats = {}


def approve_support_agent(agent_id: int, profile: dict):
    approved_support_agents.add(agent_id)
    support_profiles[agent_id] = profile


def reject_support_agent(agent_id: int):
    pending_support_requests.pop(agent_id, None)


def is_support_approved(agent_id: int) -> bool:
    return agent_id in approved_support_agents


def set_support_available(agent_id: int):
    busy_support_agents.discard(agent_id)
    available_support_agents.add(agent_id)
    save_support_presence(agent_id=agent_id, status="available")


def set_support_busy(agent_id: int):
    available_support_agents.discard(agent_id)
    busy_support_agents.add(agent_id)
    save_support_presence(agent_id=agent_id, status="busy")


def queue_support_user(user_id: int):
    if user_id not in waiting_support_users:
        waiting_support_users.append(user_id)
    for index, queued_user_id in enumerate(waiting_support_users):
        save_support_queue_user(user_id=queued_user_id, queue_position=index)


def pop_waiting_support_user():
    if not waiting_support_users:
        return None
    user_id = waiting_support_users.pop(0)
    remove_support_queue_user(user_id)
    for index, queued_user_id in enumerate(waiting_support_users):
        save_support_queue_user(user_id=queued_user_id, queue_position=index)
    return user_id


def start_support_chat(user_id: int, agent_id: int):
    support_chats[user_id] = agent_id
    support_chats[agent_id] = user_id
    set_support_busy(agent_id)
    save_support_chat(user_id=user_id, agent_id=agent_id)


def is_in_support_chat(user_id: int) -> bool:
    return user_id in support_chats


def get_support_partner(user_id: int):
    return support_chats.get(user_id)


def end_support_chat(user_id: int):
    partner_id = support_chats.pop(user_id, None)
    if partner_id is not None:
        support_chats.pop(partner_id, None)
        remove_support_chat_by_user(user_id)
        if user_id in approved_support_agents:
            busy_support_agents.discard(user_id)
            available_support_agents.add(user_id)
            save_support_presence(agent_id=user_id, status="available")
        if partner_id in approved_support_agents:
            busy_support_agents.discard(partner_id)
            available_support_agents.add(partner_id)
            save_support_presence(agent_id=partner_id, status="available")
    return partner_id


def clear_runtime_state():
    available_support_agents.clear()
    busy_support_agents.clear()
    waiting_support_users.clear()
    support_chats.clear()


def restore_runtime_state():
    clear_runtime_state()
    for row in load_support_presence():
        agent_id = row["agent_id"]
        if row["status"] == "busy":
            busy_support_agents.add(agent_id)
        else:
            available_support_agents.add(agent_id)

    for row in load_support_queue():
        waiting_support_users.append(row["user_id"])

    for row in load_support_chats():
        support_chats[row["user_id"]] = row["agent_id"]
        support_chats[row["agent_id"]] = row["user_id"]


restore_runtime_state()
