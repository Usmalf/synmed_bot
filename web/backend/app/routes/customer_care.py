from fastapi import APIRouter, Depends, HTTPException
from services.paystack import PaystackError
from pydantic import BaseModel, Field

from ..deps import require_admin, require_admin_or_customer_care
from ..services.admin_app_service import (
    clear_attention_payments,
    delete_attention_payment,
    get_admin_patient_detail,
    grant_admin_consultation_access,
    list_admin_consultations,
    list_admin_payments,
    record_admin_audit,
    revoke_admin_consultation_access,
    search_admin_records,
    send_admin_patient_document,
)
from ..services.payment_app_service import verify_web_payment
from ..services.auth_service import (
    create_customer_care_account,
    list_customer_care_accounts,
    set_customer_care_account_status,
)
from ..services.support_ai_service import (
    add_support_ticket_message,
    answer_patient_support_message,
    get_public_support_ticket,
    get_support_ticket,
    list_support_tickets,
    mark_support_ticket_messages_read,
    submit_support_ticket_feedback,
    update_support_ticket_status,
)
from ..services.internal_mail_service import (
    list_internal_messages,
    list_message_admins,
    list_message_customer_care_accounts,
    mark_internal_message_read,
    send_internal_message,
)

router = APIRouter()


class CustomerCareAccessGrantPayload(BaseModel):
    patient_id: str
    reason: str
    duration_hours: int = 24


class CustomerCarePaymentAttentionDeletePayload(BaseModel):
    reference: str = ""
    patient_id: str = ""


class CustomerCareAccountCreatePayload(BaseModel):
    email: str
    display_name: str
    password: str


class CustomerCareAccountStatusPayload(BaseModel):
    status: str


class SupportTicketStatusPayload(BaseModel):
    status: str
    note: str = ""


class SupportTicketMessagePayload(BaseModel):
    message_text: str
    contact_email: str = ""


class PublicSupportTicketFeedbackPayload(BaseModel):
    contact_email: str = ""
    rating: int | None = None
    review: str = ""
    skipped: bool = False


class CustomerCareInternalMessagePayload(BaseModel):
    recipient_role: str
    recipient_id: str
    subject: str
    body: str = ""


class CustomerCareDocumentSendPayload(BaseModel):
    document_kind: str
    document_id: str
    message: str = ""


class PublicSupportAiPayload(BaseModel):
    message: str
    escalate: bool = False
    history: list[dict] = Field(default_factory=list)
    contact_email: str = ""


@router.get("/desk")
def customer_care_desk(session: dict = Depends(require_admin_or_customer_care)):
    return {
        "payments": list_admin_payments()["payments"],
        "consultations": list_admin_consultations(100),
        "support_tickets": list_support_tickets("all", 100),
    }


@router.post("/support/ai")
def public_support_ai(payload: PublicSupportAiPayload):
    if payload.escalate and not payload.contact_email.strip():
        raise HTTPException(status_code=400, detail="Email is required before connecting to customer care.")
    return answer_patient_support_message(
        "",
        payload.message,
        payload.escalate,
        payload.history,
        contact_email=payload.contact_email,
    )


@router.get("/support/public-tickets/{ticket_id}")
def public_support_ticket(ticket_id: str, contact_email: str = ""):
    ticket = get_public_support_ticket(ticket_id, contact_email)
    if not ticket:
        raise HTTPException(status_code=404, detail="Support ticket could not be found.")
    mark_support_ticket_messages_read(ticket_id, "patient")
    return ticket


@router.post("/support/public-tickets/{ticket_id}/messages")
def public_support_ticket_message(ticket_id: str, payload: SupportTicketMessagePayload):
    if not payload.contact_email.strip():
        raise HTTPException(status_code=400, detail="Email is required to continue this support ticket.")
    ticket = get_public_support_ticket(ticket_id, payload.contact_email)
    if not ticket:
        raise HTTPException(status_code=404, detail="Support ticket could not be found.")
    result = add_support_ticket_message(
        ticket_id,
        sender_role="patient",
        sender_id=payload.contact_email.strip().lower(),
        message_text=payload.message_text,
    )
    if not result["sent"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/support/public-tickets/{ticket_id}/feedback")
def public_support_ticket_feedback(ticket_id: str, payload: PublicSupportTicketFeedbackPayload):
    result = submit_support_ticket_feedback(
        ticket_id,
        contact_email=payload.contact_email,
        rating=payload.rating,
        review=payload.review,
        skipped=payload.skipped,
    )
    if not result["saved"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.get("/search")
def customer_care_search(query: str = "", session: dict = Depends(require_admin_or_customer_care)):
    return search_admin_records(query)


@router.get("/patients/{patient_id}")
def customer_care_patient_detail(patient_id: str, session: dict = Depends(require_admin_or_customer_care)):
    result = get_admin_patient_detail(patient_id)
    if not result:
        raise HTTPException(status_code=404, detail="Patient record could not be found.")
    return result


@router.post("/patients/{patient_id}/documents/send")
def customer_care_send_patient_document(
    patient_id: str,
    payload: CustomerCareDocumentSendPayload,
    session: dict = Depends(require_admin_or_customer_care),
):
    result = send_admin_patient_document(
        admin_id=session["user_id"] if session["role"] == "admin" else 0,
        patient_id=patient_id,
        document_kind=payload.document_kind,
        document_id=payload.document_id,
        recipient_type="patient",
        message=payload.message,
    )
    if not result["sent"]:
        raise HTTPException(status_code=400, detail=result["message"])
    if session["role"] == "admin":
        record_admin_audit(
            session["user_id"],
            "customer_care_document_sent",
            "patient",
            patient_id,
            {"document_kind": payload.document_kind, "document_id": payload.document_id},
        )
    return result


@router.post("/payments/access-grant")
def customer_care_grant_access(
    payload: CustomerCareAccessGrantPayload,
    session: dict = Depends(require_admin_or_customer_care),
):
    actor_id = session["user_id"] if session["role"] == "admin" else 0
    result = grant_admin_consultation_access(
        actor_id,
        payload.patient_id,
        payload.reason,
        payload.duration_hours,
    )
    if not result["granted"]:
        raise HTTPException(status_code=404, detail=result["message"])
    if session["role"] == "admin":
        record_admin_audit(
            session["user_id"],
            "customer_care_access_granted",
            "patient",
            payload.patient_id,
            {"reason": payload.reason, "duration_hours": payload.duration_hours, "reference": result["reference"]},
        )
    return result


@router.post("/payments/access-grant/{reference}/revoke")
def customer_care_revoke_access(
    reference: str,
    session: dict = Depends(require_admin_or_customer_care),
):
    result = revoke_admin_consultation_access(reference)
    if not result["revoked"]:
        raise HTTPException(status_code=404, detail=result["message"])
    if session["role"] == "admin":
        record_admin_audit(session["user_id"], "customer_care_access_revoked", "payment", reference)
    return result


@router.post("/payments/{reference}/verify")
async def customer_care_verify_payment(reference: str, session: dict = Depends(require_admin_or_customer_care)):
    try:
        result = await verify_web_payment(reference)
    except PaystackError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if session["role"] == "admin":
        record_admin_audit(
            session["user_id"],
            "customer_care_payment_verified",
            "payment",
            reference,
            {"verified": result.get("verified"), "paystack_status": result.get("paystack_status")},
        )
    return result


@router.post("/payments/attention/delete")
def customer_care_delete_payment_attention(
    payload: CustomerCarePaymentAttentionDeletePayload,
    session: dict = Depends(require_admin_or_customer_care),
):
    result = delete_attention_payment(
        payload.reference,
        payload.patient_id,
        actor_role=session["role"],
        actor_id=session["user_id"],
    )
    if not result["deleted"]:
        raise HTTPException(status_code=400, detail=result["message"])
    if session["role"] == "admin":
        record_admin_audit(
            session["user_id"],
            "customer_care_payment_attention_deleted",
            "payment",
            payload.reference or payload.patient_id,
        )
    return result


@router.post("/payments/attention/clear")
def customer_care_clear_payment_attention(session: dict = Depends(require_admin_or_customer_care)):
    result = clear_attention_payments(actor_role=session["role"], actor_id=session["user_id"])
    if session["role"] == "admin":
        record_admin_audit(session["user_id"], "customer_care_payment_attention_cleared", "payment", "attention")
    return result


@router.get("/accounts")
def customer_care_accounts(session: dict = Depends(require_admin)):
    return {"accounts": list_customer_care_accounts()}


@router.post("/accounts")
def customer_care_create_account(
    payload: CustomerCareAccountCreatePayload,
    session: dict = Depends(require_admin),
):
    result = create_customer_care_account(
        session["user_id"],
        payload.email,
        payload.display_name,
        payload.password,
    )
    record_admin_audit(session["user_id"], "customer_care_account_created", "customer_care", result["account"]["account_id"])
    return result


@router.post("/accounts/{account_id}/status")
def customer_care_update_account_status(
    account_id: int,
    payload: CustomerCareAccountStatusPayload,
    session: dict = Depends(require_admin),
):
    result = set_customer_care_account_status(account_id, payload.status)
    record_admin_audit(
        session["user_id"],
        "customer_care_account_status_changed",
        "customer_care",
        account_id,
        {"status": payload.status},
    )
    return result


@router.get("/support-tickets")
def customer_care_support_tickets(status: str = "open", session: dict = Depends(require_admin_or_customer_care)):
    return {"tickets": list_support_tickets(status, 100)}


@router.get("/support-tickets/{ticket_id}")
def customer_care_support_ticket(ticket_id: str, session: dict = Depends(require_admin_or_customer_care)):
    ticket = get_support_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Support ticket could not be found.")
    mark_support_ticket_messages_read(ticket_id, session["role"])
    return ticket


@router.post("/support-tickets/{ticket_id}/messages")
def customer_care_send_support_ticket_message(
    ticket_id: str,
    payload: SupportTicketMessagePayload,
    session: dict = Depends(require_admin_or_customer_care),
):
    result = add_support_ticket_message(
        ticket_id,
        sender_role=session["role"],
        sender_id=session["user_id"],
        message_text=payload.message_text,
    )
    if not result["sent"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/support-tickets/{ticket_id}/status")
def customer_care_update_support_ticket(
    ticket_id: str,
    payload: SupportTicketStatusPayload,
    session: dict = Depends(require_admin_or_customer_care),
):
    result = update_support_ticket_status(
        ticket_id,
        payload.status,
        actor_role=session["role"],
        actor_id=session["user_id"],
        note=payload.note,
    )
    if not result["updated"]:
        raise HTTPException(status_code=404, detail=result["message"])
    if session["role"] == "admin":
        record_admin_audit(session["user_id"], "support_ticket_status_changed", "support_ticket", ticket_id, {"status": payload.status})
    return result


@router.get("/mail")
def customer_care_mail(session: dict = Depends(require_admin_or_customer_care)):
    mailbox_role = "customer_care" if session["role"] == "customer_care" else "admin"
    return {
        "messages": list_internal_messages(mailbox_role, session["user_id"]),
        "admins": list_message_admins(),
        "customer_care": [
            account for account in list_message_customer_care_accounts()
            if str(account["account_id"]) != str(session["user_id"])
        ],
    }


@router.post("/mail")
def customer_care_send_mail(
    payload: CustomerCareInternalMessagePayload,
    session: dict = Depends(require_admin_or_customer_care),
):
    recipient_role = payload.recipient_role if payload.recipient_role in {"admin", "customer_care"} else "admin"
    result = send_internal_message(
        sender_role=session["role"],
        sender_id=session["user_id"],
        recipient_role=recipient_role,
        recipient_id=payload.recipient_id,
        subject=payload.subject,
        body=payload.body,
    )
    if session["role"] == "admin":
        record_admin_audit(session["user_id"], "internal_message_sent", recipient_role, payload.recipient_id)
    return result


@router.post("/mail/{message_id}/read")
def customer_care_read_mail(message_id: int, session: dict = Depends(require_admin_or_customer_care)):
    mailbox_role = "customer_care" if session["role"] == "customer_care" else "admin"
    return {"updated": mark_internal_message_read(message_id, mailbox_role, session["user_id"])}
