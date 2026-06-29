from datetime import datetime, timezone
from uuid import uuid4

from database import get_connection
from services.patient_records import get_patient_by_identifier
from .admin_app_service import list_admin_payments
from .auth_service import send_plain_email

UTC = timezone.utc
PATIENT_ACTIVE_EMAIL_GRACE_SECONDS = 120


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


INTENT_KEYWORDS = {
    "login": (
        "otp", "login", "log in", "password", "sign in", "signin", "code",
        "unable to send otp", "email", "verify", "verification", "recover",
    ),
    "payment": (
        "payment", "pay", "paid", "access", "grant", "receipt", "reference",
        "debit", "charged", "paystack", "proceed", "blocked",
    ),
    "documents": (
        "prescription", "investigation", "report", "document", "download",
        "result", "file", "attachment", "medical report",
    ),
    "appointments": (
        "appointment", "book", "follow up", "follow-up", "schedule", "reschedule",
        "reminder",
    ),
    "consultation": (
        "doctor", "queue", "waiting", "connect", "consultation", "chat",
        "return to chat", "start consultation", "end chat", "review card",
    ),
    "clinical": (
        "diagnosis", "drug", "medicine", "symptom", "pain", "fever", "treatment",
        "bleeding", "chest pain", "breathing", "pregnant", "collapse", "unconscious",
    ),
}

ESCALATION_WORDS = (
    "human", "agent", "customer care", "support staff", "real person",
    "representative", "talk to someone", "call me", "report this",
)

FRUSTRATION_WORDS = (
    "still", "again", "not working", "does nothing", "keeps saying",
    "unable", "failed", "error", "blocked", "stuck", "not been", "cannot",
)

AFFIRMATIVE_WORDS = ("yes", "yeah", "yep", "ok", "okay", "please", "do it", "send it", "escalate")
RESET_WORDS = ("start over", "reset", "new issue", "main menu", "menu")

DIRECT_TOPIC_ALIASES = {
    "login": (
        "otp problem", "otp still not coming", "i changed my email", "login problem",
        "sign in problem", "password problem",
    ),
    "payment": (
        "payment issue", "still blocked", "i was debited", "access issue",
        "payment access", "grant access",
    ),
    "documents": (
        "documents", "document", "prescription missing", "report missing",
        "investigation missing", "medical report", "download document",
    ),
    "appointments": (
        "appointment", "appointments", "booking failed", "follow-up issue",
        "follow up issue", "schedule issue",
    ),
    "consultation": (
        "consultation", "return to chat failed", "doctor not connecting",
        "queue issue", "start consultation", "return to chat",
    ),
    "clinical": (
        "symptoms", "symptom", "clinical", "medical advice", "diagnosis",
    ),
}


def _history_text(history: list[dict]) -> str:
    return " ".join(str(item.get("text") or "") for item in history[-6:]).lower()


def _last_assistant_text(history: list[dict]) -> str:
    for item in reversed(history or []):
        if item.get("role") == "assistant":
            return str(item.get("text") or "").lower()
    return ""


def _topic_for(message: str, history: list[dict] | None = None) -> str:
    text = message.lower()
    stripped = text.strip()
    for topic, aliases in DIRECT_TOPIC_ALIASES.items():
        if stripped in aliases:
            return topic

    current_scores = {}
    for topic, keywords in INTENT_KEYWORDS.items():
        current_scores[topic] = sum(1 for keyword in keywords if keyword in text)
    current_topic, current_score = max(current_scores.items(), key=lambda item: item[1])
    if current_score:
        return current_topic

    context = _history_text(history or [])
    scores = {}
    for topic, keywords in INTENT_KEYWORDS.items():
        scores[topic] = sum(1 for keyword in keywords if keyword in context)

    if any(word in text for word in AFFIRMATIVE_WORDS):
        for topic, keywords in INTENT_KEYWORDS.items():
            if any(keyword in context for keyword in keywords):
                scores[topic] = scores.get(topic, 0) + 1

    best_topic, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score:
        return best_topic
    return "general"


def _wants_escalation(message: str, history: list[dict] | None = None) -> bool:
    text = message.lower()
    if any(word in text for word in ESCALATION_WORDS):
        return True
    last_assistant = _last_assistant_text(history or [])
    if "customer care" in last_assistant and "ticket" in last_assistant:
        return any(word in text for word in AFFIRMATIVE_WORDS)
    return False


def _sounds_stuck(message: str) -> bool:
    text = message.lower()
    return any(word in text for word in FRUSTRATION_WORDS)


def _wants_reset(message: str) -> bool:
    text = message.lower()
    return any(word in text for word in RESET_WORDS)


def _latest_patient_payment(patient_id: str) -> dict | None:
    for payment in list_admin_payments()["payments"]:
        if str(payment.get("patient_id") or "").upper() == str(patient_id or "").upper():
            return payment
    return None


def _quick_replies_for(topic: str, *, escalated: bool = False, patient: dict | None = None) -> list[str]:
    if escalated:
        return ["Add more details", "Start over"]
    if topic == "login":
        return ["OTP still not coming", "I changed my email", "Talk to agent"]
    if topic == "payment":
        if patient:
            return ["Still blocked", "I was debited", "Talk to agent"]
        return ["I need to sign in", "Talk to agent", "Start over"]
    if topic == "documents":
        return ["Prescription missing", "Report missing", "Talk to agent"]
    if topic == "appointments":
        return ["Booking failed", "Follow-up issue", "Talk to agent"]
    if topic == "consultation":
        return ["Return to chat failed", "Doctor not connecting", "Talk to agent"]
    if topic == "clinical":
        return ["Start consultation", "Return to chat", "Start over"]
    return ["OTP problem", "Payment issue", "Documents", "Talk to agent"]


def _reply_for(topic: str, message: str, patient: dict | None, history: list[dict] | None = None) -> tuple[str, bool]:
    patient_id = patient["hospital_number"] if patient else ""
    payment = _latest_patient_payment(patient_id) if patient_id else None
    stuck = _sounds_stuck(message)

    if topic == "login":
        if stuck:
            return (
                "This sounds like a persistent login or OTP problem. I will send this to customer care so they can check the account and delivery channel.",
                True,
            )
        return (
            "For OTP or login issues: use the newest code, check that the email on your account is correct, and try Resend OTP once. "
            "If it still does not arrive, reply 'agent' and I will send it to customer care.",
            False,
        )
    if topic == "payment":
        if not patient:
            return (
                "I can explain payment access, but I need a signed-in patient account to trace a specific payment. "
                "Please sign in, then reopen support. If you need a human now, reply 'agent' and I will create a support ticket.",
                False,
            )
        if payment and payment.get("access_active"):
            return (
                f"Your consultation access appears active for hospital number {patient_id}. Return to Patient Home and start or continue consultation. "
                "If the page still blocks you, reply 'still blocked' and I will send it to customer care.",
                False,
            )
        if payment and payment.get("status") == "verified":
            return (
                "I can see a completed payment record, but the access window may need review. I will send this to customer care so they can check and grant access if appropriate.",
                True,
            )
        return (
            "I could not confirm active consultation access from your latest payment record. I will send this to customer care so they can trace the payment or grant access where appropriate.",
            True,
        )
    if topic == "documents":
        if stuck:
            return (
                "This sounds like a missing or inaccessible document. I will send it to customer care so they can check the prescription, investigation, or report record.",
                True,
            )
        if not patient:
            return (
                "For prescriptions, investigations, and reports, sign in as a patient and open Patient Home, then Documents. "
                "If a document is still missing after sign-in, choose 'Talk to agent' and customer care will check it.",
                False,
            )
        return (
            "For prescriptions, investigations, or reports: open Patient Home, then Documents. "
            "If the file is missing after the doctor created it, reply 'agent' and I will send it to customer care.",
            False,
        )
    if topic == "appointments":
        return (
            "For appointments or follow-up: open Patient Home, then Book Appointment or Follow-Up. "
            "If payment or scheduling fails, tell me what failed and I can route it to customer care.",
            False,
        )
    if topic == "consultation":
        if stuck:
            return (
                "This consultation flow sounds stuck. I will send this to customer care so they can check your queue, access, or return-to-chat state.",
                True,
            )
        return (
            "To start or return to a consultation, use Patient Home. If you paid already, SynMed should reuse an active access window. "
            "If you are blocked or cannot return to chat, tell me what you see and I can escalate it.",
            False,
        )
    if topic == "clinical":
        urgent = any(word in message.lower() for word in ("chest pain", "can't breathe", "cannot breathe", "unconscious", "collapse", "severe bleeding"))
        if urgent:
            return (
                "This may be urgent. Please seek emergency care immediately or contact local emergency services. "
                "I cannot provide diagnosis or treatment here, but you should not wait for chat support for severe symptoms.",
                False,
            )
        return (
            "I cannot give diagnosis, prescriptions, or medical advice. A licensed doctor needs to review clinical symptoms. "
            "Please start a consultation or return to your active chat so a doctor can assess you.",
            False,
        )
    return (
        "I can help with login, OTP, payment access, documents, appointments, and consultation navigation. "
        "Tell me what happened and I can either guide you or pass it to customer care.",
        False,
    )


def _patient_contact_email(patient: dict | None, contact_email: str = "") -> str:
    return ((patient or {}).get("email") or contact_email or "").strip().lower()


def _notify_support_ticket_email(ticket: dict, subject: str, body: str) -> None:
    email = (ticket.get("contact_email") or "").strip()
    if not email:
        return
    try:
        send_plain_email(email, subject, body)
    except Exception:
        return


def _ticket_patient_recently_active(ticket_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT created_at
            FROM support_ticket_messages
            WHERE ticket_id = ? AND sender_role = 'patient'
            ORDER BY id DESC
            LIMIT 1
            """,
            (ticket_id,),
        )
        row = cursor.fetchone()
    last_patient_message_at = _parse_iso(row["created_at"] if row else None)
    if not last_patient_message_at:
        return False
    if last_patient_message_at.tzinfo is None:
        last_patient_message_at = last_patient_message_at.replace(tzinfo=UTC)
    elapsed = datetime.now(UTC) - last_patient_message_at.astimezone(UTC)
    return elapsed.total_seconds() <= PATIENT_ACTIVE_EMAIL_GRACE_SECONDS


def create_support_ticket(patient: dict | None, topic: str, message: str, ai_reply: str, contact_email: str = "") -> dict:
    ticket_id = f"SUP-{uuid4().hex[:10].upper()}"
    now = _now_iso()
    patient_id = patient["hospital_number"] if patient else ""
    patient_name = patient["name"] if patient else "Patient"
    ticket_email = _patient_contact_email(patient, contact_email)
    summary = f"Patient message: {message.strip()}\n\nAI response: {ai_reply.strip()}"
    thread_message = message.strip()
    if "\n" in thread_message:
        thread_message = thread_message.splitlines()[-1].strip()
    if thread_message.lower().startswith("user:"):
        thread_message = thread_message.split(":", 1)[1].strip()
    if thread_message.lower().startswith("patient message:"):
        thread_message = thread_message.split(":", 1)[1].strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO support_tickets (
                ticket_id, patient_id, patient_name, contact_email, topic, summary, status,
                source, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'open', 'ai_support', ?, ?)
            """,
            (ticket_id, patient_id, patient_name, ticket_email, topic, summary, now, now),
        )
        cursor.execute(
            """
            INSERT INTO support_ticket_messages (
                ticket_id, sender_role, sender_id, message_text, created_at
            )
            VALUES (?, 'patient', ?, ?, ?)
            """,
            (ticket_id, patient_id, thread_message or message.strip(), now),
        )
        cursor.execute(
            """
            INSERT INTO support_ticket_messages (
                ticket_id, sender_role, sender_id, message_text, created_at
            )
            VALUES (?, 'assistant', 'ai_support', ?, ?)
            """,
            (ticket_id, ai_reply.strip(), now),
        )
        cursor.execute(
            """
            INSERT INTO support_ticket_logs (
                ticket_id, actor_role, actor_id, action, note, created_at
            )
            VALUES (?, 'assistant', 'ai_support', 'opened', ?, ?)
            """,
            (ticket_id, f"Ticket opened from {topic} support flow.", now),
        )
        conn.commit()
    return {
        "ticket_id": ticket_id,
        "patient_id": patient_id,
        "patient_name": patient_name,
        "contact_email": ticket_email,
        "topic": topic,
        "summary": summary,
        "status": "open",
        "created_at": now,
        "updated_at": now,
    }


def _support_summary(history: list[dict], message: str) -> str:
    recent = [
        f"{item.get('role', 'user')}: {str(item.get('text') or '').strip()}"
        for item in history[-6:]
        if str(item.get("text") or "").strip()
    ]
    recent.append(f"user: {message.strip()}")
    return "\n".join(recent)


def answer_patient_support_message(
    patient_identifier: str,
    message: str,
    escalate: bool = False,
    history: list[dict] | None = None,
    contact_email: str = "",
) -> dict:
    patient = get_patient_by_identifier(patient_identifier)
    history = history or []
    if _wants_reset(message):
        return {
            "reply": "No problem. Tell me what you need help with: OTP, payment access, documents, appointment, or consultation.",
            "topic": "general",
            "escalated": False,
            "ticket": None,
            "suggested_escalation": False,
            "quick_replies": _quick_replies_for("general", patient=patient),
            "confidence": "guided",
        }
    topic = _topic_for(message, history)
    reply, suggested_escalation = _reply_for(topic, message, patient, history)
    explicit_escalation = escalate or _wants_escalation(message, history)
    should_escalate = explicit_escalation or suggested_escalation
    if explicit_escalation:
        reply = (
            "All our customer-care agents are currently busy, but your message has been sent to the support queue. "
            "An agent will join this chat as soon as possible."
        )
    ticket_message = _support_summary(history, message) if should_escalate else message
    ticket = create_support_ticket(patient, topic, ticket_message, reply, contact_email=contact_email) if should_escalate else None
    return {
        "reply": reply,
        "topic": topic,
        "escalated": bool(ticket),
        "ticket": ticket,
        "suggested_escalation": suggested_escalation,
        "quick_replies": _quick_replies_for(topic, escalated=bool(ticket), patient=patient),
        "confidence": "guided" if topic != "general" else "low",
    }


def list_support_tickets(status: str = "open", limit: int = 100) -> list[dict]:
    normalized_status = (status or "open").strip().lower()
    where_clause = "" if normalized_status == "all" else "WHERE status = ?"
    params = [] if normalized_status == "all" else [normalized_status]
    params.append(max(1, min(limit, 250)))
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT ticket_id, patient_id, patient_name, contact_email, topic, summary, status,
                   source, created_at, updated_at, resolved_at,
                   (
                       SELECT COUNT(*)
                       FROM support_ticket_messages stm
                       WHERE stm.ticket_id = support_tickets.ticket_id
                         AND stm.sender_role = 'patient'
                         AND stm.read_at IS NULL
                   ) AS unread_patient_messages
            FROM support_tickets
            {where_clause}
            ORDER BY datetime(COALESCE(updated_at, created_at)) DESC
            LIMIT ?
            """,
            params,
        )
        return [dict(row) for row in cursor.fetchall()]


def get_support_ticket(ticket_id: str, patient_id: str = "") -> dict | None:
    with get_connection() as conn:
        cursor = conn.cursor()
        params = [ticket_id]
        patient_clause = ""
        if patient_id:
            patient_clause = "AND patient_id = ?"
            params.append(patient_id)
        cursor.execute(
            f"""
            SELECT ticket_id, patient_id, patient_name, contact_email, topic, summary, status,
                   source, created_at, updated_at, resolved_at
            FROM support_tickets
            WHERE ticket_id = ? {patient_clause}
            """,
            params,
        )
        ticket = cursor.fetchone()
        if not ticket:
            return None
        cursor.execute(
            """
            SELECT id, ticket_id, sender_role, sender_id, message_text, read_at, created_at
            FROM support_ticket_messages
            WHERE ticket_id = ?
            ORDER BY id ASC
            """,
            (ticket_id,),
        )
        messages = [dict(row) for row in cursor.fetchall()]
        cursor.execute(
            """
            SELECT id, ticket_id, actor_role, actor_id, action, note, created_at
            FROM support_ticket_logs
            WHERE ticket_id = ?
            ORDER BY id DESC
            """,
            (ticket_id,),
        )
        logs = [dict(row) for row in cursor.fetchall()]
        cursor.execute(
            """
            SELECT id, ticket_id, patient_id, contact_email, rating, review, skipped, created_at
            FROM support_ticket_feedback
            WHERE ticket_id = ?
            """,
            (ticket_id,),
        )
        feedback_row = cursor.fetchone()
    return {**dict(ticket), "messages": messages, "logs": logs, "feedback": dict(feedback_row) if feedback_row else None}


def get_public_support_ticket(ticket_id: str, contact_email: str) -> dict | None:
    email = (contact_email or "").strip().lower()
    if not email:
        return None
    ticket = get_support_ticket(ticket_id)
    if not ticket or (ticket.get("contact_email") or "").strip().lower() != email:
        return None
    return ticket


def mark_support_ticket_messages_read(ticket_id: str, reader_role: str) -> None:
    if reader_role not in {"patient", "customer_care", "admin"}:
        return
    if reader_role == "patient":
        sender_roles = ("customer_care", "admin", "assistant")
    else:
        sender_roles = ("patient",)
    placeholders = ",".join("?" for _ in sender_roles)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            UPDATE support_ticket_messages
            SET read_at = COALESCE(read_at, ?)
            WHERE ticket_id = ?
              AND sender_role IN ({placeholders})
            """,
            (_now_iso(), ticket_id, *sender_roles),
        )
        conn.commit()


def submit_support_ticket_feedback(
    ticket_id: str,
    *,
    patient_id: str = "",
    contact_email: str = "",
    rating: int | None = None,
    review: str = "",
    skipped: bool = False,
) -> dict:
    ticket = get_support_ticket(ticket_id, patient_id=patient_id)
    if not ticket:
        return {"saved": False, "message": "Support ticket could not be found."}
    normalized_email = (contact_email or "").strip().lower()
    if not patient_id and (ticket.get("contact_email") or "").strip().lower() != normalized_email:
        return {"saved": False, "message": "Support ticket could not be found."}
    if not skipped and (rating is None or rating < 1 or rating > 5):
        return {"saved": False, "message": "Choose a rating between 1 and 5."}
    now = _now_iso()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO support_ticket_feedback (
                ticket_id, patient_id, contact_email, rating, review, skipped, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticket_id) DO UPDATE SET
                patient_id = excluded.patient_id,
                contact_email = excluded.contact_email,
                rating = excluded.rating,
                review = excluded.review,
                skipped = excluded.skipped,
                created_at = excluded.created_at
            """,
            (
                ticket_id,
                patient_id or ticket.get("patient_id") or "",
                normalized_email or ticket.get("contact_email") or "",
                None if skipped else rating,
                "" if skipped else review.strip(),
                1 if skipped else 0,
                now,
            ),
        )
        cursor.execute(
            """
            INSERT INTO support_ticket_logs (
                ticket_id, actor_role, actor_id, action, note, created_at
            )
            VALUES (?, 'patient', ?, ?, ?, ?)
            """,
            (
                ticket_id,
                patient_id or normalized_email,
                "feedback_skipped" if skipped else "feedback_submitted",
                "" if skipped else f"Rating: {rating}",
                now,
            ),
        )
        conn.commit()
    return {"saved": True, "message": "Thank you for the feedback." if not skipped else "Feedback skipped."}


def add_support_ticket_message(
    ticket_id: str,
    *,
    sender_role: str,
    sender_id: str | int = "",
    message_text: str,
    patient_id: str = "",
) -> dict:
    body = (message_text or "").strip()
    if not body:
        return {"sent": False, "message": "Message cannot be empty."}
    ticket = get_support_ticket(ticket_id, patient_id=patient_id)
    if not ticket:
        return {"sent": False, "message": "Support ticket could not be found."}
    if ticket["status"] != "open":
        return {"sent": False, "message": "This support ticket is closed. Reopen it before sending a new message."}
    now = _now_iso()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO support_ticket_messages (
                ticket_id, sender_role, sender_id, message_text, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (ticket_id, sender_role, str(sender_id or ""), body, now),
        )
        message_id = cursor.lastrowid
        cursor.execute(
            """
            UPDATE support_tickets
            SET updated_at = ?
            WHERE ticket_id = ?
            """,
            (now, ticket_id),
        )
        conn.commit()
    if sender_role in {"customer_care", "admin"} and not _ticket_patient_recently_active(ticket_id):
        _notify_support_ticket_email(
            ticket,
            f"No response yet on SynMed support ticket {ticket_id}",
            f"Hello {ticket.get('patient_name') or 'Patient'},\n\nCustomer care replied while you were away from support chat:\n\n{body}\n\nOpen SynMed support to continue the conversation.\n\nSynMed Support",
        )
    return {
        "sent": True,
        "message": "Support message sent.",
        "entry": {
            "id": message_id,
            "ticket_id": ticket_id,
            "sender_role": sender_role,
            "sender_id": str(sender_id or ""),
            "message_text": body,
            "read_at": None,
            "created_at": now,
        },
    }


def update_support_ticket_status(
    ticket_id: str,
    status: str,
    actor_role: str = "system",
    actor_id: str | int = "",
    note: str = "",
) -> dict:
    normalized_status = (status or "").strip().lower()
    if normalized_status not in {"open", "resolved"}:
        return {"updated": False, "message": "Unsupported ticket status."}
    now = _now_iso()
    action = "reopened" if normalized_status == "open" else "closed"
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE support_tickets
            SET status = ?, updated_at = ?, resolved_at = ?
            WHERE ticket_id = ?
            """,
            (normalized_status, now, now if normalized_status == "resolved" else None, ticket_id),
        )
        updated = cursor.rowcount > 0
        if updated:
            cursor.execute(
                """
                INSERT INTO support_ticket_logs (
                    ticket_id, actor_role, actor_id, action, note, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (ticket_id, actor_role, str(actor_id or ""), action, note.strip(), now),
            )
        conn.commit()
    if updated:
        ticket = get_support_ticket(ticket_id)
        if ticket and normalized_status == "resolved":
            _notify_support_ticket_email(
                ticket,
                f"SynMed support ticket {ticket_id} closed",
                f"Hello {ticket.get('patient_name') or 'Patient'},\n\nYour SynMed support ticket {ticket_id} has been closed.\n\n{note.strip() or 'If you still need help, open customer support again and start a new ticket.'}\n\nSynMed Support",
            )
    return {
        "updated": updated,
        "message": "Ticket updated." if updated else "Support ticket could not be found.",
    }
