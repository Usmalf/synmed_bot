TOP_LEVEL_STATE_KEYS = (
    "patient_flow_state",
    "patient_record",
    "payment_context",
    "appointment_context",
    "admin_pending_action",
    "admin_patient_edit_data",
    "admin_doctor_edit_data",
    "clinical_document_draft",
    "clinical_letter_draft",
    "pending_consultation_note",
    "pending_save_diagnosis",
    "followup_state",
    "support_request_state",
    "support_request_name",
)


def reset_interactive_state(user_data: dict, preserve: set[str] | None = None):
    preserve = preserve or set()
    for key in TOP_LEVEL_STATE_KEYS:
        if key not in preserve:
            user_data.pop(key, None)
