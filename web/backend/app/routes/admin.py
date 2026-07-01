from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from services.paystack import PaystackError
from services.backups import create_database_backup, create_full_backup_archive, get_backup_status
from pydantic import BaseModel

from ..deps import require_admin
from ..services.admin_app_service import (
    approve_doctor_application,
    clear_attention_payments,
    create_health_tip,
    delete_attention_payment,
    delete_health_tip,
    get_admin_consultation,
    get_admin_alerts,
    get_admin_delivery_settings,
    get_admin_patient_detail,
    get_admin_ratings,
    get_admin_summary,
    grant_admin_consultation_access,
    list_admin_audit_logs,
    list_admin_consultations,
    list_admin_patients,
    list_admin_payments,
    list_health_tips,
    reject_doctor_application,
    record_admin_audit,
    revoke_admin_consultation_access,
    search_admin_records,
    send_admin_patient_document,
    send_admin_delivery_test,
    send_doctor_license_reminder,
    set_doctor_account_status,
    update_health_tip,
    update_admin_alert_state,
    update_admin_email_branding_settings,
    update_admin_payment_settings,
)
from ..services.medical_report_app_service import assign_medical_report_request, list_admin_medical_report_requests
from ..services.partner_app_service import create_partner_facility, list_partner_facilities, update_partner_status
from ..services.payment_app_service import verify_web_payment
from ..services.internal_mail_service import (
    list_internal_messages,
    list_message_customer_care_accounts,
    list_message_doctors,
    mark_internal_message_read,
    send_internal_message,
)
from ..services.support_ai_service import get_support_ticket, list_support_tickets, update_support_ticket_status

router = APIRouter()


class HealthTipPayload(BaseModel):
    eyebrow: str
    title: str
    body: str
    sort_order: int = 0
    is_active: bool = True
    audience: str = "landing"


class MedicalReportAssignmentPayload(BaseModel):
    doctor_id: str


class DoctorApplicationRejectPayload(BaseModel):
    reason: str = ""


class DoctorAccountActionPayload(BaseModel):
    reason: str = ""


class DeliveryTestPayload(BaseModel):
    channel: str
    target: str


class AdminDocumentSendPayload(BaseModel):
    document_kind: str
    document_id: str
    recipient_type: str
    doctor_id: str = ""
    message: str = ""


class AdminInternalMessagePayload(BaseModel):
    recipient_doctor_id: int | None = None
    recipient_role: str = "doctor"
    recipient_id: str = ""
    subject: str
    body: str = ""


class AdminSupportTicketStatusPayload(BaseModel):
    status: str
    note: str = ""


class AdminAccessGrantPayload(BaseModel):
    patient_id: str
    reason: str
    duration_hours: int = 24


class AdminPaymentAttentionDeletePayload(BaseModel):
    reference: str = ""
    patient_id: str = ""


class AdminPaymentSettingsPayload(BaseModel):
    new_patient_fee: int
    returning_patient_fee: int
    new_patient_label: str
    returning_patient_label: str
    followup_fee: int
    followup_label: str
    medical_report_fee: int
    medical_report_label: str


class AdminEmailBrandingPayload(BaseModel):
    brand_name: str
    logo_url: str = ""
    support_address: str = ""
    footer_text: str = ""


class AdminPartnerPayload(BaseModel):
    name: str
    partner_type: str
    email: str = ""
    phone: str = ""
    address: str = ""
    contact_person: str = ""
    status: str = "pending"
    notes: str = ""


class AdminPartnerStatusPayload(BaseModel):
    status: str


@router.get("/summary")
def admin_summary(session: dict = Depends(require_admin)):
    return get_admin_summary()


@router.get("/alerts")
def admin_alerts(session: dict = Depends(require_admin)):
    return get_admin_alerts(session["user_id"])


@router.post("/alerts/{alert_id}/review")
def admin_review_alert(alert_id: str, session: dict = Depends(require_admin)):
    result = update_admin_alert_state(session["user_id"], alert_id, "review")
    if not result["updated"]:
        raise HTTPException(status_code=404, detail=result["message"])
    record_admin_audit(session["user_id"], "admin_alert_reviewed", "admin_alert", alert_id)
    return result


@router.delete("/alerts/{alert_id}")
def admin_dismiss_alert(alert_id: str, session: dict = Depends(require_admin)):
    result = update_admin_alert_state(session["user_id"], alert_id, "dismiss")
    if not result["updated"]:
        status_code = 400 if result["message"] == "Critical alerts cannot be dismissed." else 404
        raise HTTPException(status_code=status_code, detail=result["message"])
    record_admin_audit(session["user_id"], "admin_alert_dismissed", "admin_alert", alert_id)
    return result


@router.get("/audit-logs")
def admin_audit_logs(limit: int = 100, session: dict = Depends(require_admin)):
    return {"logs": list_admin_audit_logs(limit)}


@router.get("/mail")
def admin_mail(session: dict = Depends(require_admin)):
    return {
        "messages": list_internal_messages("admin", session["user_id"]),
        "doctors": list_message_doctors(),
        "customer_care": list_message_customer_care_accounts(),
    }


@router.post("/mail")
def admin_send_mail(payload: AdminInternalMessagePayload, session: dict = Depends(require_admin)):
    recipient_role = payload.recipient_role if payload.recipient_role in {"doctor", "customer_care", "admin"} else "doctor"
    recipient_id = payload.recipient_id or payload.recipient_doctor_id
    if recipient_role == "doctor" and payload.recipient_doctor_id:
        recipient_id = payload.recipient_doctor_id
    result = send_internal_message(
        sender_role="admin",
        sender_id=session["user_id"],
        recipient_role=recipient_role,
        recipient_id=recipient_id,
        subject=payload.subject,
        body=payload.body,
    )
    record_admin_audit(
        session["user_id"],
        "internal_message_sent",
        recipient_role,
        recipient_id,
    )
    return result


@router.post("/mail/{message_id}/read")
def admin_read_mail(message_id: int, session: dict = Depends(require_admin)):
    return {"updated": mark_internal_message_read(message_id, "admin", session["user_id"])}


@router.get("/support-tickets")
def admin_support_tickets(status: str = "all", session: dict = Depends(require_admin)):
    return {"tickets": list_support_tickets(status, 250)}


@router.get("/support-tickets/{ticket_id}")
def admin_support_ticket(ticket_id: str, session: dict = Depends(require_admin)):
    ticket = get_support_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Support ticket could not be found.")
    return ticket


@router.post("/support-tickets/{ticket_id}/status")
def admin_update_support_ticket(
    ticket_id: str,
    payload: AdminSupportTicketStatusPayload,
    session: dict = Depends(require_admin),
):
    result = update_support_ticket_status(
        ticket_id,
        payload.status,
        actor_role="admin",
        actor_id=session["user_id"],
        note=payload.note,
    )
    if not result["updated"]:
        raise HTTPException(status_code=404, detail=result["message"])
    record_admin_audit(session["user_id"], "support_ticket_status_changed", "support_ticket", ticket_id, {"status": payload.status, "note": payload.note})
    return result


@router.get("/patients")
def admin_patients(query: str = "", limit: int = 100, session: dict = Depends(require_admin)):
    return {"patients": list_admin_patients(query, limit)}


@router.get("/payments")
def admin_payments(session: dict = Depends(require_admin)):
    return list_admin_payments()


@router.post("/payments/access-grant")
def admin_grant_consultation_access(
    payload: AdminAccessGrantPayload,
    session: dict = Depends(require_admin),
):
    result = grant_admin_consultation_access(
        session["user_id"],
        payload.patient_id,
        payload.reason,
        payload.duration_hours,
    )
    if not result["granted"]:
        raise HTTPException(status_code=404, detail=result["message"])
    record_admin_audit(
        session["user_id"],
        "consultation_access_granted",
        "patient",
        payload.patient_id,
        {"reason": payload.reason, "duration_hours": payload.duration_hours, "reference": result["reference"]},
    )
    return result


@router.post("/payments/access-grant/{reference}/revoke")
def admin_revoke_consultation_access(reference: str, session: dict = Depends(require_admin)):
    result = revoke_admin_consultation_access(reference)
    if not result["revoked"]:
        raise HTTPException(status_code=404, detail=result["message"])
    record_admin_audit(
        session["user_id"],
        "consultation_access_revoked",
        "payment",
        reference,
    )
    return result


@router.post("/payments/{reference}/verify")
async def admin_verify_payment(reference: str, session: dict = Depends(require_admin)):
    try:
        result = await verify_web_payment(reference)
    except PaystackError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_admin_audit(
        session["user_id"],
        "payment_verified",
        "payment",
        reference,
        {"verified": result.get("verified"), "paystack_status": result.get("paystack_status")},
    )
    return result


@router.post("/payments/attention/delete")
def admin_delete_payment_attention(payload: AdminPaymentAttentionDeletePayload, session: dict = Depends(require_admin)):
    result = delete_attention_payment(
        payload.reference,
        payload.patient_id,
        actor_role="admin",
        actor_id=session["user_id"],
    )
    if not result["deleted"]:
        raise HTTPException(status_code=400, detail=result["message"])
    record_admin_audit(
        session["user_id"],
        "payment_attention_deleted",
        "payment",
        payload.reference or payload.patient_id,
    )
    return result


@router.post("/payments/attention/clear")
def admin_clear_payment_attention(session: dict = Depends(require_admin)):
    result = clear_attention_payments(actor_role="admin", actor_id=session["user_id"])
    record_admin_audit(session["user_id"], "payment_attention_cleared", "payment", "attention")
    return result


@router.get("/search")
def admin_search(query: str = "", session: dict = Depends(require_admin)):
    return search_admin_records(query)


@router.get("/patients/{patient_id}")
def admin_patient_detail(patient_id: str, session: dict = Depends(require_admin)):
    result = get_admin_patient_detail(patient_id)
    if not result:
        raise HTTPException(status_code=404, detail="Patient record could not be found.")
    return result


@router.post("/patients/{patient_id}/documents/send")
def admin_send_patient_document(
    patient_id: str,
    payload: AdminDocumentSendPayload,
    session: dict = Depends(require_admin),
):
    result = send_admin_patient_document(
        admin_id=session["user_id"],
        patient_id=patient_id,
        document_kind=payload.document_kind,
        document_id=payload.document_id,
        recipient_type=payload.recipient_type,
        doctor_id=payload.doctor_id,
        message=payload.message,
    )
    if not result["sent"]:
        raise HTTPException(status_code=400, detail=result["message"])
    record_admin_audit(
        session["user_id"],
        "clinical_document_sent",
        payload.recipient_type,
        payload.doctor_id or patient_id,
        {"patient_id": patient_id, "document_id": payload.document_id},
    )
    return result


@router.get("/consultations")
def admin_consultations(limit: int = 100, session: dict = Depends(require_admin)):
    return {"consultations": list_admin_consultations(limit)}


@router.get("/consultations/{consultation_id}")
def admin_consultation_detail(consultation_id: str, session: dict = Depends(require_admin)):
    result = get_admin_consultation(consultation_id)
    if not result:
        raise HTTPException(status_code=404, detail="Consultation could not be found.")
    return result


@router.get("/ratings")
def admin_ratings(session: dict = Depends(require_admin)):
    return get_admin_ratings()


@router.get("/delivery-settings")
def admin_delivery_settings(session: dict = Depends(require_admin)):
    return get_admin_delivery_settings()


@router.get("/backups/status")
def admin_backup_status(session: dict = Depends(require_admin)):
    return get_backup_status()


@router.post("/backups/database")
def admin_database_backup(session: dict = Depends(require_admin)):
    try:
        backup = create_database_backup()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    record_admin_audit(
        session["user_id"],
        "database_backup_created",
        "backup",
        backup["filename"],
        f"Database backup downloaded: {backup['size']} bytes",
    )
    return FileResponse(
        path=backup["path"],
        media_type="application/octet-stream",
        filename=backup["filename"],
    )


@router.post("/backups/full")
def admin_full_backup(session: dict = Depends(require_admin)):
    try:
        backup = create_full_backup_archive()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    record_admin_audit(
        session["user_id"],
        "full_backup_created",
        "backup",
        backup["filename"],
        f"Full backup downloaded: {backup['size']} bytes",
    )
    return FileResponse(
        path=backup["path"],
        media_type="application/zip",
        filename=backup["filename"],
    )


@router.post("/delivery-settings/test")
def admin_delivery_test(payload: DeliveryTestPayload, session: dict = Depends(require_admin)):
    result = send_admin_delivery_test(payload.channel, payload.target)
    if not result["sent"]:
        raise HTTPException(status_code=503, detail=result["message"])
    record_admin_audit(
        session["user_id"],
        "delivery_test_sent",
        "delivery_channel",
        payload.channel,
        {"target": payload.target},
    )
    return result


@router.put("/settings/payments")
def admin_update_payment_settings(payload: AdminPaymentSettingsPayload, session: dict = Depends(require_admin)):
    result = update_admin_payment_settings(payload.model_dump())
    if not result["updated"]:
        raise HTTPException(status_code=400, detail=result["message"])
    record_admin_audit(
        session["user_id"],
        "payment_settings_updated",
        "settings",
        "payments",
        result["payments"],
    )
    return result


@router.put("/settings/email-branding")
def admin_update_email_branding(payload: AdminEmailBrandingPayload, session: dict = Depends(require_admin)):
    result = update_admin_email_branding_settings(payload.model_dump())
    if not result["updated"]:
        raise HTTPException(status_code=400, detail=result["message"])
    record_admin_audit(
        session["user_id"],
        "email_branding_settings_updated",
        "settings",
        "email_branding",
        result["email_branding"],
    )
    return result


@router.post("/doctor-applications/{doctor_id}/approve")
def admin_approve_doctor_application(doctor_id: int, session: dict = Depends(require_admin)):
    result = approve_doctor_application(doctor_id)
    if not result["updated"]:
        raise HTTPException(status_code=404, detail=result["message"])
    record_admin_audit(session["user_id"], "doctor_application_approved", "doctor", doctor_id)
    return result


@router.post("/doctor-applications/{doctor_id}/reject")
def admin_reject_doctor_application(
    doctor_id: int,
    payload: DoctorApplicationRejectPayload,
    session: dict = Depends(require_admin),
):
    result = reject_doctor_application(doctor_id, payload.reason)
    if not result["updated"]:
        raise HTTPException(status_code=404, detail=result["message"])
    record_admin_audit(
        session["user_id"],
        "doctor_application_rejected",
        "doctor",
        doctor_id,
        {"reason": payload.reason},
    )
    return result


@router.post("/doctors/{doctor_id}/suspend")
def admin_suspend_doctor(
    doctor_id: int,
    payload: DoctorAccountActionPayload,
    session: dict = Depends(require_admin),
):
    result = set_doctor_account_status(doctor_id, "suspend", payload.reason)
    if not result["updated"]:
        raise HTTPException(status_code=404, detail=result["message"])
    record_admin_audit(
        session["user_id"],
        "doctor_suspended",
        "doctor",
        doctor_id,
        {"reason": payload.reason},
    )
    return result


@router.post("/doctors/{doctor_id}/reactivate")
def admin_reactivate_doctor(doctor_id: int, session: dict = Depends(require_admin)):
    result = set_doctor_account_status(doctor_id, "reactivate")
    if not result["updated"]:
        raise HTTPException(status_code=404, detail=result["message"])
    record_admin_audit(session["user_id"], "doctor_reactivated", "doctor", doctor_id)
    return result


@router.post("/doctors/{doctor_id}/license-reminder")
def admin_send_doctor_license_reminder(doctor_id: int, session: dict = Depends(require_admin)):
    result = send_doctor_license_reminder(doctor_id)
    if not result["sent"]:
        raise HTTPException(status_code=503, detail=result["message"])
    record_admin_audit(session["user_id"], "licence_reminder_sent", "doctor", doctor_id)
    return result


@router.get("/health-tips")
def admin_health_tips(session: dict = Depends(require_admin)):
    return {"tips": list_health_tips(include_inactive=True)}


@router.post("/health-tips")
def admin_create_health_tip(payload: HealthTipPayload, session: dict = Depends(require_admin)):
    tip = create_health_tip(payload.model_dump())
    record_admin_audit(session["user_id"], "health_tip_created", "health_tip", tip["id"])
    return {"created": True, "tip": tip}


@router.put("/health-tips/{tip_id}")
def admin_update_health_tip(tip_id: int, payload: HealthTipPayload, session: dict = Depends(require_admin)):
    tip = update_health_tip(tip_id, payload.model_dump())
    if not tip:
        raise HTTPException(status_code=404, detail="Health tip could not be found.")
    record_admin_audit(session["user_id"], "health_tip_updated", "health_tip", tip_id)
    return {"updated": True, "tip": tip}


@router.delete("/health-tips/{tip_id}")
def admin_delete_health_tip(tip_id: int, session: dict = Depends(require_admin)):
    deleted = delete_health_tip(tip_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Health tip could not be found.")
    record_admin_audit(session["user_id"], "health_tip_deleted", "health_tip", tip_id)
    return {"deleted": True}


@router.get("/partners")
def admin_partners(session: dict = Depends(require_admin)):
    return list_partner_facilities()


@router.post("/partners")
def admin_create_partner(payload: AdminPartnerPayload, session: dict = Depends(require_admin)):
    result = create_partner_facility(payload.model_dump())
    if not result["created"]:
        raise HTTPException(status_code=400, detail=result["message"])
    record_admin_audit(session["user_id"], "partner_created", "partner", result["partner"]["partner_id"])
    return result


@router.post("/partners/{partner_id}/status")
def admin_update_partner_status(
    partner_id: str,
    payload: AdminPartnerStatusPayload,
    session: dict = Depends(require_admin),
):
    result = update_partner_status(partner_id, payload.status)
    if not result["updated"]:
        raise HTTPException(status_code=404, detail=result["message"])
    record_admin_audit(
        session["user_id"],
        "partner_status_updated",
        "partner",
        partner_id,
        {"status": payload.status},
    )
    return result


@router.get("/medical-report-requests")
def admin_medical_report_requests(session: dict = Depends(require_admin)):
    return list_admin_medical_report_requests()


@router.post("/medical-report-requests/{request_id}/assign")
def admin_assign_medical_report_request(
    request_id: str,
    payload: MedicalReportAssignmentPayload,
    session: dict = Depends(require_admin),
):
    result = assign_medical_report_request(request_id, payload.doctor_id)
    if not result["updated"]:
        raise HTTPException(status_code=404, detail=result["message"])
    record_admin_audit(
        session["user_id"],
        "medical_report_assigned",
        "medical_report",
        request_id,
        {"doctor_id": payload.doctor_id},
    )
    return result
