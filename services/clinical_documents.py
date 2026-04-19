import json
import os
import textwrap
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from database import get_connection
from synmed_utils.doctor_profiles import doctor_profiles


LAGOS_TZ = timezone(timedelta(hours=1))
ROOT_DIR = Path(__file__).resolve().parent.parent
GENERATED_DOCUMENTS_DIR = ROOT_DIR / "generated_documents"
DEFAULT_LOGO_CANDIDATES = (
    ROOT_DIR / "assets" / "synmed_logo.png",
    ROOT_DIR / "assets" / "synmed_logo.jpg",
    ROOT_DIR / "assets" / "synmed_logo.jpeg",
    ROOT_DIR / "logo.png",
    ROOT_DIR / "logo.jpg",
    ROOT_DIR / "logo.jpeg",
)
BRAND_BLUE = colors.HexColor("#045B76")
BRAND_GOLD = colors.HexColor("#F0B24D")
BRAND_DARK = colors.HexColor("#12212A")
TEXT_DARK = colors.HexColor("#20313A")
TEXT_MUTED = colors.HexColor("#586972")


def _timestamp_parts():
    issued_at = datetime.now(LAGOS_TZ)
    return issued_at, issued_at.strftime("%Y-%m-%d"), issued_at.strftime("%H:%M:%S")


def _doctor_display_name(doctor_id: int) -> str:
    profile = doctor_profiles.get(doctor_id, {})
    name = profile.get("name") or "Doctor"
    return f"Dr. {name}"


def _patient_line(patient_details: dict, key: str, fallback: str = "N/A") -> str:
    return str(patient_details.get(key, fallback))


def _logo_path() -> Path | None:
    configured = os.getenv("SYNMED_LOGO_PATH")
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            path = ROOT_DIR / path
        if path.exists():
            return path

    for candidate in DEFAULT_LOGO_CANDIDATES:
        if candidate.exists():
            return candidate

    return None


def _motto_text() -> str:
    return os.getenv("SYNMED_MOTTO", "").strip()


def _doctor_signature_path(doctor_id: int) -> Path | None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT signature_path
            FROM doctors
            WHERE telegram_id = ?
            """,
            (doctor_id,),
        )
        row = cursor.fetchone()
    if not row or not row["signature_path"]:
        return None

    path = Path(row["signature_path"])
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path if path.exists() else None


def _relative_asset_path(filename: str) -> str:
    return f"generated_documents/{filename}"


def _public_asset_url(filename: str) -> str:
    return f"/generated-documents/{filename}"


def _absolute_asset_path(asset_path: str | None) -> Path | None:
    if not asset_path:
        return None
    path = Path(asset_path)
    if not path.is_absolute():
        path = ROOT_DIR / asset_path
    return path if path.exists() else None


def _format_prescription_medications(medications: list[dict]) -> str:
    return "\n".join(
        f"{index}. {med['route']} {med['name']} {med['dose']} {med['duration']}"
        for index, med in enumerate(medications, start=1)
    )


def _build_document_content(
    *,
    title: str,
    patient_details: dict,
    diagnosis: str,
    items_label: str,
    items_text: str,
    doctor_name: str,
    notes: str,
    date_text: str,
    time_text: str,
    extra_lines: list[str] | None = None,
) -> str:
    lines = [
        title,
        "",
        "Patient Biodata",
        f"Name: {_patient_line(patient_details, 'name')}",
        f"Age: {_patient_line(patient_details, 'age')}",
        f"Gender: {_patient_line(patient_details, 'gender')}",
        f"Hospital Number: {_patient_line(patient_details, 'hospital_number')}",
        "",
        f"Diagnosis: {diagnosis}",
        "",
        items_label,
        items_text,
        "",
        f"Doctor: {doctor_name}",
        f"Date: {date_text}",
        f"Time: {time_text}",
    ]
    if extra_lines:
        lines.extend([""] + extra_lines)
    if notes:
        lines.extend(["", "Notes", notes])
    return "\n".join(lines)


def _draw_wrapped_text(pdf: canvas.Canvas, text: str, x: float, y: float, *, width: int = 88, leading: int = 14):
    for paragraph in str(text or "").splitlines() or [""]:
        wrapped = textwrap.wrap(paragraph, width=width) or [""]
        for line in wrapped:
            pdf.drawString(x, y, line)
            y -= leading
    return y


def _draw_section(pdf: canvas.Canvas, title: str, text: str, *, x: float, y: float, width: int = 88):
    pdf.setFont("Helvetica-Bold", 11)
    pdf.setFillColor(BRAND_BLUE)
    pdf.drawString(x, y, title)
    y -= 16
    pdf.setFont("Helvetica", 10)
    pdf.setFillColor(TEXT_DARK)
    return _draw_wrapped_text(pdf, text, x, y, width=width)


def _render_signature(pdf: canvas.Canvas, doctor_id: int, doctor_name: str, *, x: float, y: float):
    signature_path = _doctor_signature_path(doctor_id)
    if signature_path:
        try:
            pdf.drawImage(ImageReader(str(signature_path)), x, y - 6, width=120, height=40, mask="auto")
        except Exception:
            pdf.setFont("Times-Italic", 14)
            pdf.drawString(x, y + 8, doctor_name)
    else:
        pdf.setFont("Times-Italic", 14)
        pdf.drawString(x, y + 8, doctor_name)


def _create_pdf_document(*, filename: str, payload: dict) -> BytesIO:
    GENERATED_DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    path = GENERATED_DOCUMENTS_DIR / filename
    pdf = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    margin = 46
    top = height - margin

    pdf.setFillColor(BRAND_DARK)
    pdf.rect(0, height - 110, width, 110, fill=1, stroke=0)
    pdf.setFillColor(BRAND_BLUE)
    pdf.rect(0, height - 118, width, 8, fill=1, stroke=0)

    logo = _logo_path()
    if logo:
        try:
            pdf.drawImage(ImageReader(str(logo)), margin, height - 98, width=64, height=64, mask="auto")
        except Exception:
            pass

    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 24)
    pdf.drawCentredString(width / 2, height - 52, "SynMed Telehealth")
    motto = _motto_text()
    if motto:
        pdf.setFillColor(BRAND_GOLD)
        pdf.setFont("Helvetica-Oblique", 10)
        pdf.drawCentredString(width / 2, height - 68, motto)

    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawCentredString(width / 2, height - 88, payload["title"].upper())

    y = top - 94
    pdf.setStrokeColor(colors.HexColor("#D6E1E6"))
    pdf.setFillColor(colors.HexColor("#F7FAFC"))
    pdf.roundRect(margin, y - 44, width - (margin * 2), 40, 10, fill=1, stroke=1)
    pdf.setFillColor(TEXT_DARK)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(margin + 14, y - 20, f"Document: {payload['title']}")
    pdf.drawString(margin + 190, y - 20, f"Date: {payload['date_text']}")
    pdf.drawString(margin + 340, y - 20, f"Time: {payload['time_text']}")
    pdf.drawString(margin + 450, y - 20, f"Hospital No: {payload['hospital_number']}")
    y -= 66

    pdf.setStrokeColor(colors.HexColor("#D6E1E6"))
    pdf.setFillColor(colors.HexColor("#F8FBFC"))
    pdf.roundRect(margin, y - 78, width - (margin * 2), 74, 10, fill=1, stroke=1)
    pdf.setFillColor(TEXT_DARK)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(margin + 14, y - 18, f"Patient: {_patient_line(payload['patient_details'], 'name')}")
    pdf.drawString(margin + 260, y - 18, f"Age: {_patient_line(payload['patient_details'], 'age')}")
    pdf.drawString(margin + 340, y - 18, f"Gender: {_patient_line(payload['patient_details'], 'gender')}")
    pdf.drawString(margin + 430, y - 18, f"Phone: {_patient_line(payload['patient_details'], 'phone')}")
    pdf.setFont("Helvetica", 10)
    history_preview = _patient_line(payload["patient_details"], "history", "N/A")
    y = _draw_section(pdf, "History / Symptoms", history_preview, x=margin + 14, y=y - 42, width=95)
    y -= 16

    y = _draw_section(pdf, "Diagnosis", payload["diagnosis"], x=margin, y=y, width=95)
    y -= 18

    items_title = payload["items_label"]
    items_text = "\n".join(payload.get("items", [])) if payload.get("items") else payload.get("items_text", "")
    y = _draw_section(pdf, items_title, items_text, x=margin, y=y, width=95)
    y -= 18

    if payload.get("extra_lines"):
        y = _draw_section(pdf, "Additional Details", "\n".join(payload["extra_lines"]), x=margin, y=y, width=95)
        y -= 18

    if payload.get("notes"):
        y = _draw_section(pdf, "Clinical Note", payload["notes"], x=margin, y=y, width=95)
        y -= 18

    footer_y = max(100, y - 20)
    pdf.line(margin, footer_y, margin + 140, footer_y)
    _render_signature(pdf, payload["doctor_id"], payload["doctor_name"], x=margin, y=footer_y + 10)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.setFillColor(TEXT_DARK)
    pdf.drawString(margin, footer_y - 16, payload["doctor_name"])
    pdf.setFont("Helvetica", 9)
    pdf.setFillColor(TEXT_MUTED)
    pdf.drawString(margin, footer_y - 30, "Doctor Name / Signature")
    pdf.drawString(width - margin - 165, footer_y - 16, f"Issued on {payload['date_text']} at {payload['time_text']}")
    pdf.drawString(margin, 36, "Generated by SynMed Telehealth")

    pdf.save()
    buffer = BytesIO(path.read_bytes())
    buffer.name = filename
    buffer.seek(0)
    return buffer


def create_prescription_document(
    *,
    consultation_id: str,
    doctor_id: int,
    patient_id: int,
    patient_details: dict,
    diagnosis: str,
    medications_text: str = "",
    medications: list[dict] | None = None,
    notes: str = "",
):
    issued_at, date_text, time_text = _timestamp_parts()
    doctor_name = _doctor_display_name(doctor_id)
    medications = medications or []
    if medications and not medications_text:
        medications_text = _format_prescription_medications(medications)

    content = _build_document_content(
        title="Prescription",
        patient_details=patient_details,
        diagnosis=diagnosis,
        items_label="Prescribed Medications",
        items_text=medications_text,
        doctor_name=doctor_name,
        notes=notes,
        date_text=date_text,
        time_text=time_text,
    )
    rx_id = uuid4().hex
    medication_payload = medications or [
        {"text": line.strip()}
        for line in medications_text.splitlines()
        if line.strip()
    ]
    filename = f"synmed_prescription_{consultation_id[:8]}_{rx_id[:6]}.pdf"
    file_buffer = _create_pdf_document(
        filename=filename,
        payload={
            "title": "Prescription",
            "doctor_id": doctor_id,
            "doctor_name": doctor_name,
            "hospital_number": _patient_line(patient_details, "hospital_number"),
            "patient_details": patient_details,
            "diagnosis": diagnosis,
            "items_label": "Prescribed Medications",
            "items": [line.strip() for line in medications_text.splitlines() if line.strip()],
            "items_text": medications_text,
            "notes": notes,
            "date_text": date_text,
            "time_text": time_text,
        },
    )
    asset_path = _relative_asset_path(filename)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE prescriptions SET is_latest = 0 WHERE consultation_id = ?", (consultation_id,))
        cursor.execute(
            """
            INSERT INTO prescriptions (
                rx_id, consultation_id, doctor_id, patient_id, version,
                medication_json, notes, is_latest, created_at, asset_path, asset_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rx_id,
                consultation_id,
                str(doctor_id),
                str(patient_id),
                1,
                json.dumps({"diagnosis": diagnosis, "medications": medication_payload}),
                notes,
                1,
                issued_at.isoformat(),
                asset_path,
                "application/pdf",
            ),
        )
        conn.commit()

    return {
        "document_id": rx_id,
        "filename": filename,
        "file": file_buffer,
        "content": content,
        "asset_path": asset_path,
        "asset_url": _public_asset_url(filename),
        "asset_type": "application/pdf",
    }


def create_investigation_document(
    *,
    consultation_id: str,
    doctor_id: int,
    patient_id: int,
    patient_details: dict,
    diagnosis: str,
    tests_text: str,
    notes: str = "",
):
    issued_at, date_text, time_text = _timestamp_parts()
    doctor_name = _doctor_display_name(doctor_id)
    content = _build_document_content(
        title="Investigation Request",
        patient_details=patient_details,
        diagnosis=diagnosis,
        items_label="Requested Investigations",
        items_text=tests_text,
        doctor_name=doctor_name,
        notes=notes,
        date_text=date_text,
        time_text=time_text,
    )
    request_id = uuid4().hex
    filename = f"synmed_investigation_{consultation_id[:8]}_{request_id[:6]}.pdf"
    file_buffer = _create_pdf_document(
        filename=filename,
        payload={
            "title": "Investigation Request",
            "doctor_id": doctor_id,
            "doctor_name": doctor_name,
            "hospital_number": _patient_line(patient_details, "hospital_number"),
            "patient_details": patient_details,
            "diagnosis": diagnosis,
            "items_label": "Requested Investigations",
            "items": [line.strip() for line in tests_text.splitlines() if line.strip()],
            "items_text": tests_text,
            "notes": notes,
            "date_text": date_text,
            "time_text": time_text,
        },
    )
    asset_path = _relative_asset_path(filename)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO investigation_requests (
                request_id, consultation_id, doctor_id, patient_id,
                diagnosis, tests_text, notes, created_at, asset_path, asset_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                consultation_id,
                str(doctor_id),
                str(patient_id),
                diagnosis,
                tests_text,
                notes,
                issued_at.isoformat(),
                asset_path,
                "application/pdf",
            ),
        )
        conn.commit()

    return {
        "document_id": request_id,
        "filename": filename,
        "file": file_buffer,
        "content": content,
        "asset_path": asset_path,
        "asset_url": _public_asset_url(filename),
        "asset_type": "application/pdf",
    }


def create_referral_document(
    *,
    consultation_id: str,
    doctor_id: int,
    patient_id: int,
    patient_details: dict,
    diagnosis: str,
    referral_note: str,
    referred_hospital: str,
):
    issued_at, date_text, time_text = _timestamp_parts()
    doctor_name = _doctor_display_name(doctor_id)
    content = _build_document_content(
        title="Referral Note",
        patient_details=patient_details,
        diagnosis=diagnosis,
        items_label="Referral Note",
        items_text=referral_note,
        doctor_name=doctor_name,
        notes="",
        date_text=date_text,
        time_text=time_text,
        extra_lines=[f"Referred Hospital: {referred_hospital}"],
    )
    filename = f"synmed_referral_{consultation_id[:8]}_{uuid4().hex[:6]}.pdf"
    file_buffer = _create_pdf_document(
        filename=filename,
        payload={
            "title": "Referral Note",
            "doctor_id": doctor_id,
            "doctor_name": doctor_name,
            "hospital_number": _patient_line(patient_details, "hospital_number"),
            "patient_details": patient_details,
            "diagnosis": diagnosis,
            "items_label": "Referral Note",
            "items": [line.strip() for line in referral_note.splitlines() if line.strip()],
            "items_text": referral_note,
            "notes": "",
            "date_text": date_text,
            "time_text": time_text,
            "extra_lines": [f"Referred Hospital: {referred_hospital}"],
        },
    )
    asset_path = _relative_asset_path(filename)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO clinical_letters (
                letter_id, consultation_id, doctor_id, patient_id, document_type,
                diagnosis, body_text, target_hospital, created_at, asset_path, asset_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid4().hex,
                consultation_id,
                str(doctor_id),
                str(patient_id),
                "referral",
                diagnosis,
                referral_note,
                referred_hospital,
                issued_at.isoformat(),
                asset_path,
                "application/pdf",
            ),
        )
        conn.commit()
    return {
        "filename": filename,
        "file": file_buffer,
        "content": content,
        "asset_path": asset_path,
        "asset_url": _public_asset_url(filename),
        "asset_type": "application/pdf",
    }


def create_medical_report_document(
    *,
    consultation_id: str,
    doctor_id: int,
    patient_id: int,
    patient_details: dict,
    diagnosis: str,
    report_note: str,
):
    issued_at, date_text, time_text = _timestamp_parts()
    doctor_name = _doctor_display_name(doctor_id)
    content = _build_document_content(
        title="Medical Report",
        patient_details=patient_details,
        diagnosis=diagnosis,
        items_label="Medical Report",
        items_text=report_note,
        doctor_name=doctor_name,
        notes="",
        date_text=date_text,
        time_text=time_text,
    )
    filename = f"synmed_medical_report_{consultation_id[:8]}_{uuid4().hex[:6]}.pdf"
    file_buffer = _create_pdf_document(
        filename=filename,
        payload={
            "title": "Medical Report",
            "doctor_id": doctor_id,
            "doctor_name": doctor_name,
            "hospital_number": _patient_line(patient_details, "hospital_number"),
            "patient_details": patient_details,
            "diagnosis": diagnosis,
            "items_label": "Medical Report",
            "items": [line.strip() for line in report_note.splitlines() if line.strip()],
            "items_text": report_note,
            "notes": "",
            "date_text": date_text,
            "time_text": time_text,
        },
    )
    asset_path = _relative_asset_path(filename)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO clinical_letters (
                letter_id, consultation_id, doctor_id, patient_id, document_type,
                diagnosis, body_text, target_hospital, created_at, asset_path, asset_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid4().hex,
                consultation_id,
                str(doctor_id),
                str(patient_id),
                "medical_report",
                diagnosis,
                report_note,
                "",
                issued_at.isoformat(),
                asset_path,
                "application/pdf",
            ),
        )
        conn.commit()
    return {
        "filename": filename,
        "file": file_buffer,
        "content": content,
        "asset_path": asset_path,
        "asset_url": _public_asset_url(filename),
        "asset_type": "application/pdf",
    }


def regenerate_prescription_document(row, patient_details: dict):
    medications = []
    diagnosis = "N/A"
    try:
        payload = json.loads(row["medication_json"] or "{}")
        diagnosis = payload.get("diagnosis") or "N/A"
        medications = payload.get("medications") or []
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    doctor_id = int(row["doctor_id"])
    doctor_name = _doctor_display_name(doctor_id)
    issued_at = row["created_at"] or datetime.now(LAGOS_TZ).isoformat()
    issued_at_value = datetime.fromisoformat(issued_at)
    if issued_at_value.tzinfo is None:
        issued_at_value = issued_at_value.replace(tzinfo=timezone.utc).astimezone(LAGOS_TZ)
    else:
        issued_at_value = issued_at_value.astimezone(LAGOS_TZ)
    date_text = issued_at_value.strftime("%Y-%m-%d")
    time_text = issued_at_value.strftime("%H:%M:%S")
    medications_text = _format_prescription_medications(medications)
    filename = f"synmed_prescription_{row['consultation_id'][:8]}_{str(row['document_id'])[:6]}.pdf"
    file_buffer = _create_pdf_document(
        filename=filename,
        payload={
            "title": "Prescription",
            "doctor_id": doctor_id,
            "doctor_name": doctor_name,
            "hospital_number": _patient_line(patient_details, "hospital_number"),
            "patient_details": patient_details,
            "diagnosis": diagnosis,
            "items_label": "Prescribed Medications",
            "items": [line.strip() for line in medications_text.splitlines() if line.strip()],
            "items_text": medications_text,
            "notes": row["notes"] or "",
            "date_text": date_text,
            "time_text": time_text,
        },
    )
    asset_path = _relative_asset_path(filename)
    document = {
        "filename": filename,
        "file": file_buffer,
        "asset_path": asset_path,
        "asset_type": "application/pdf",
        "asset_url": _public_asset_url(filename),
    }
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE prescriptions
            SET asset_path = ?, asset_type = ?
            WHERE rx_id = ?
            """,
            (document["asset_path"], document["asset_type"], row["document_id"]),
        )
        conn.commit()
    return document


def regenerate_investigation_document(row, patient_details: dict):
    doctor_id = int(row["doctor_id"])
    doctor_name = _doctor_display_name(doctor_id)
    issued_at = row["created_at"] or datetime.now(LAGOS_TZ).isoformat()
    issued_at_value = datetime.fromisoformat(issued_at)
    if issued_at_value.tzinfo is None:
        issued_at_value = issued_at_value.replace(tzinfo=timezone.utc).astimezone(LAGOS_TZ)
    else:
        issued_at_value = issued_at_value.astimezone(LAGOS_TZ)
    date_text = issued_at_value.strftime("%Y-%m-%d")
    time_text = issued_at_value.strftime("%H:%M:%S")
    filename = f"synmed_investigation_{row['consultation_id'][:8]}_{str(row['document_id'])[:6]}.pdf"
    file_buffer = _create_pdf_document(
        filename=filename,
        payload={
            "title": "Investigation Request",
            "doctor_id": doctor_id,
            "doctor_name": doctor_name,
            "hospital_number": _patient_line(patient_details, "hospital_number"),
            "patient_details": patient_details,
            "diagnosis": row["diagnosis"] or "N/A",
            "items_label": "Requested Investigations",
            "items": [line.strip() for line in (row["tests_text"] or "").splitlines() if line.strip()],
            "items_text": row["tests_text"] or "",
            "notes": row["notes"] or "",
            "date_text": date_text,
            "time_text": time_text,
        },
    )
    asset_path = _relative_asset_path(filename)
    document = {
        "filename": filename,
        "file": file_buffer,
        "asset_path": asset_path,
        "asset_type": "application/pdf",
        "asset_url": _public_asset_url(filename),
    }
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE investigation_requests
            SET asset_path = ?, asset_type = ?
            WHERE request_id = ?
            """,
            (document["asset_path"], document["asset_type"], row["document_id"]),
        )
        conn.commit()
    return document


def load_existing_document_bytes(asset_path: str | None):
    path = _absolute_asset_path(asset_path)
    if not path:
        return None
    buffer = BytesIO(path.read_bytes())
    buffer.name = path.name
    buffer.seek(0)
    return buffer
