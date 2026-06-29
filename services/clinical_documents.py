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
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from database import get_connection
from services import storage_service
from synmed_utils.doctor_profiles import doctor_profiles


LAGOS_TZ = timezone(timedelta(hours=1))
ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_LOGO_CANDIDATES = (
    ROOT_DIR / "assets" / "synmed_logo.png",
    ROOT_DIR / "assets" / "synmed_logo.jpg",
    ROOT_DIR / "assets" / "synmed_logo.jpeg",
    ROOT_DIR / "logo.png",
    ROOT_DIR / "logo.jpg",
    ROOT_DIR / "logo.jpeg",
)
BRAND_BLUE = "#045B76"
BRAND_GOLD = "#F0B24D"
BRAND_DARK = "#12212A"
TEXT_DARK = "#20313A"


def _timestamp_parts():
    issued_at = datetime.now(LAGOS_TZ)
    return issued_at, issued_at.strftime("%Y-%m-%d"), issued_at.strftime("%H:%M")


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


def _doctor_display_name(doctor_id: int) -> str:
    profile = doctor_profiles.get(doctor_id, {})
    name = profile.get("name") or "Doctor"
    return f"Dr. {name}"


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
    signature_path = row["signature_path"] if row and row["signature_path"] else None
    if not signature_path:
        return None
    path = Path(signature_path)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path if path.exists() else None


def _relative_asset_path(filename: str) -> str:
    return f"generated_documents/{filename}"


def _absolute_asset_path(asset_path: str | None) -> Path | None:
    if not asset_path:
        return None
    path = storage_service.local_path(asset_path)
    return path if path.exists() else None


def _public_asset_url(filename: str) -> str:
    return f"/generated-documents/{filename}"


def load_existing_document_bytes(asset_path: str | None):
    path = _absolute_asset_path(asset_path)
    if not path:
        return None
    buffer = BytesIO(path.read_bytes())
    buffer.name = path.name
    buffer.seek(0)
    return buffer


def _patient_value(patient_details: dict, key: str, fallback: str = "N/A") -> str:
    return str(patient_details.get(key, fallback) or fallback)


def _wrap_lines(text: str, width: int = 92) -> list[str]:
    output = []
    for paragraph in (text or "").splitlines() or [""]:
        output.extend(textwrap.wrap(paragraph.strip(), width=width) or [paragraph.strip() or ""])
    return output


def _draw_wrapped(pdf: canvas.Canvas, lines: list[str], x: float, y: float, *, font_name: str = "Helvetica", font_size: int = 11, gap: int = 15):
    pdf.setFont(font_name, font_size)
    cursor = y
    for line in lines:
        pdf.drawString(x, cursor, line)
        cursor -= gap
    return cursor


def _draw_header(pdf: canvas.Canvas, page_width: float, page_height: float, title: str):
    pdf.setFillColor(colors.HexColor(BRAND_DARK))
    pdf.rect(0, page_height - 104, page_width, 104, fill=1, stroke=0)

    logo = _logo_path()
    if logo:
        try:
            pdf.drawImage(ImageReader(str(logo)), 40, page_height - 88, width=48, height=48, mask="auto")
        except Exception:
            pass

    header_title = "SynMed Telehealth"
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString((page_width - stringWidth(header_title, "Helvetica-Bold", 22)) / 2, page_height - 38, header_title)

    motto = _motto_text()
    if motto:
        pdf.setFillColor(colors.HexColor(BRAND_GOLD))
        pdf.setFont("Helvetica-Oblique", 10)
        pdf.drawString((page_width - stringWidth(motto, "Helvetica-Oblique", 10)) / 2, page_height - 54, motto)

    pdf.setFillColor(colors.HexColor("#DCECF1"))
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString((page_width - stringWidth(title, "Helvetica-Bold", 14)) / 2, page_height - 74, title)


def _draw_signature(pdf: canvas.Canvas, doctor_id: int, doctor_name: str, x: float, y: float):
    pdf.setStrokeColor(colors.HexColor("#C7D6DE"))
    pdf.line(x, y, x + 180, y)

    signature_path = _doctor_signature_path(doctor_id)
    if signature_path:
        try:
            pdf.drawImage(
                ImageReader(str(signature_path)),
                x + 4,
                y + 8,
                width=96,
                height=34,
                mask="auto",
                preserveAspectRatio=True,
            )
        except Exception:
            pass

    pdf.setFillColor(colors.HexColor(TEXT_DARK))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(x, y - 12, doctor_name)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(x, y - 26, "Doctor Signature / Name")


def _build_content(
    *,
    title: str,
    patient_details: dict,
    diagnosis: str,
    history: str,
    body_label: str,
    body_text: str,
    doctor_name: str,
    date_text: str,
    time_text: str,
    notes: str = "",
):
    lines = [
        title,
        "",
        f"Patient: {_patient_value(patient_details, 'name')}",
        f"Age: {_patient_value(patient_details, 'age')}",
        f"Hospital Number: {_patient_value(patient_details, 'hospital_number', _patient_value(patient_details, 'patient_id'))}",
        f"Date: {date_text}",
        f"Time: {time_text}",
        "",
        f"History: {history}",
        "",
        f"Diagnosis: {diagnosis}",
        "",
        f"{body_label}:",
        body_text,
        "",
        f"Doctor: {doctor_name}",
    ]
    if notes:
        lines.extend(["", notes])
    return "\n".join(lines)


def _render_pdf(
    *,
    filename: str,
    title: str,
    doctor_id: int,
    doctor_name: str,
    patient_details: dict,
    diagnosis: str,
    history: str,
    body_label: str,
    body_text: str,
    date_text: str,
    time_text: str,
    notes: str = "",
    include_history: bool = True,
):
    path = storage_service.local_path(_relative_asset_path(filename), create_parent=True)

    pdf = canvas.Canvas(str(path), pagesize=A4)
    page_width, page_height = A4
    margin = 42
    y = page_height - 130

    _draw_header(pdf, page_width, page_height, title.upper())

    pdf.setFillColor(colors.HexColor("#F6FAFC"))
    pdf.setStrokeColor(colors.HexColor(BRAND_BLUE))
    pdf.roundRect(margin, y - 18, page_width - (margin * 2), 34, 8, stroke=1, fill=1)
    pdf.setFillColor(colors.HexColor(TEXT_DARK))
    pdf.setFont("Helvetica-Bold", 10)
    meta_line = (
        f"Document: {title}    Date: {date_text} {time_text}    "
        f"Hospital No: {_patient_value(patient_details, 'hospital_number', _patient_value(patient_details, 'patient_id'))}"
    )
    pdf.drawString(margin + 10, y - 5, meta_line)
    y -= 42

    def section(label: str):
        nonlocal y
        pdf.setFillColor(colors.HexColor(BRAND_BLUE))
        pdf.roundRect(margin, y - 16, 150, 18, 6, fill=1, stroke=0)
        pdf.setFillColor(colors.white)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(margin + 10, y - 10, label)
        y -= 28

    def ensure_space(required_height: int):
        nonlocal y
        if y - required_height < 160:
            pdf.showPage()
            _draw_header(pdf, page_width, page_height, title.upper())
            y = page_height - 130

    section("Patient Biodata")
    pdf.setFillColor(colors.HexColor(TEXT_DARK))
    pdf.setFont("Helvetica", 11)
    pdf.drawString(margin + 4, y, f"Name: {_patient_value(patient_details, 'name')}")
    pdf.drawString(margin + 260, y, f"Hospital No: {_patient_value(patient_details, 'hospital_number', _patient_value(patient_details, 'patient_id'))}")
    y -= 16
    pdf.drawString(margin + 4, y, f"Age: {_patient_value(patient_details, 'age')}")
    pdf.drawString(margin + 260, y, f"Gender: {_patient_value(patient_details, 'gender')}")
    y -= 16
    pdf.drawString(margin + 4, y, f"Phone: {_patient_value(patient_details, 'phone')}")
    pdf.drawString(margin + 260, y, f"Allergy: {_patient_value(patient_details, 'allergy', 'None recorded')}")
    y -= 16
    pdf.drawString(margin + 4, y, f"Medical Conditions: {_patient_value(patient_details, 'medical_conditions', 'None recorded')}")
    y -= 22

    if include_history:
        history_lines = _wrap_lines(history or "Not recorded")
        ensure_space(42 + (len(history_lines) * 14))
        section("History")
        history_text_y = y - 10
        pdf.setFillColor(colors.HexColor(TEXT_DARK))
        pdf.setStrokeColor(colors.HexColor("#D9E4EA"))
        history_box_height = max(58, 30 + (len(history_lines) * 14))
        history_box_y = history_text_y - history_box_height + 14
        pdf.roundRect(margin, history_box_y, page_width - (margin * 2), history_box_height, 8, stroke=1, fill=0)
        _draw_wrapped(pdf, history_lines, margin + 8, history_text_y, gap=14)
        y = history_box_y - 22

    diagnosis_lines = _wrap_lines(diagnosis or "Not recorded")
    ensure_space(42 + (len(diagnosis_lines) * 14))
    section("Diagnosis")
    diagnosis_text_y = y - 10
    pdf.setFillColor(colors.HexColor(TEXT_DARK))
    pdf.setStrokeColor(colors.HexColor("#D9E4EA"))
    diagnosis_box_height = max(58, 30 + (len(diagnosis_lines) * 14))
    diagnosis_box_y = diagnosis_text_y - diagnosis_box_height + 14
    pdf.roundRect(margin, diagnosis_box_y, page_width - (margin * 2), diagnosis_box_height, 8, stroke=1, fill=0)
    _draw_wrapped(pdf, diagnosis_lines, margin + 8, diagnosis_text_y, font_name="Helvetica-Bold", gap=14)
    y = diagnosis_box_y - 24

    body_lines = _wrap_lines(body_text or "Not recorded", 88)
    ensure_space(110 + (len(body_lines) * 18))
    section(body_label)
    body_text_y = y - 10
    pdf.setFillColor(colors.HexColor(TEXT_DARK))
    pdf.setStrokeColor(colors.HexColor(BRAND_GOLD if title.lower() == "prescription" else BRAND_BLUE))
    body_box_height = max(110, 44 + (len(body_lines) * 18))
    body_box_y = body_text_y - body_box_height + 14
    pdf.roundRect(margin, body_box_y, page_width - (margin * 2), body_box_height, 10, stroke=1, fill=0)
    pdf.setFont("Helvetica", 11)
    _draw_wrapped(pdf, body_lines, margin + 12, body_text_y, gap=16)
    y = body_box_y - 28

    if notes:
        note_lines = _wrap_lines(notes)
        ensure_space(104 + (len(note_lines) * 18))
        section("Additional Notes")
        notes_text_y = y - 10
        pdf.setFillColor(colors.HexColor(TEXT_DARK))
        pdf.setStrokeColor(colors.HexColor("#D9E4EA"))
        notes_box_height = max(92, 36 + (len(note_lines) * 18))
        notes_box_y = notes_text_y - notes_box_height + 14
        pdf.roundRect(margin, notes_box_y, page_width - (margin * 2), notes_box_height, 8, stroke=1, fill=0)
        _draw_wrapped(pdf, note_lines, margin + 8, notes_text_y, gap=16)
        y = notes_box_y - 18

    _draw_signature(pdf, doctor_id, doctor_name, margin + 4, 126)
    pdf.setFillColor(colors.HexColor(TEXT_DARK))
    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(page_width - margin, 112, f"Issued: {date_text} {time_text}")
    pdf.save()

    buffer = BytesIO(path.read_bytes())
    buffer.name = filename
    buffer.seek(0)
    return buffer


def _draw_document_footer(pdf: canvas.Canvas, page_width: float, margin: float):
    pdf.setStrokeColor(colors.HexColor("#D9E4EA"))
    pdf.line(margin, 58, page_width - margin, 58)
    pdf.setFillColor(colors.HexColor("#667983"))
    pdf.setFont("Helvetica", 8)
    pdf.drawCentredString(
        page_width / 2,
        42,
        "SynMed Telehealth | This document was generated electronically from the patient's SynMed consultation record.",
    )


def _render_medical_report_pdf(
    *,
    filename: str,
    doctor_id: int,
    doctor_name: str,
    patient_details: dict,
    referral_note: str,
    date_text: str,
    time_text: str,
):
    path = storage_service.local_path(_relative_asset_path(filename), create_parent=True)

    pdf = canvas.Canvas(str(path), pagesize=A4)
    page_width, page_height = A4
    margin = 42
    y = page_height - 130

    def start_page():
        nonlocal y
        _draw_header(pdf, page_width, page_height, "MEDICAL REPORT")
        y = page_height - 130

    def section_label(label: str):
        nonlocal y
        pdf.setFillColor(colors.HexColor(BRAND_BLUE))
        pdf.roundRect(margin, y - 16, 150, 18, 6, fill=1, stroke=0)
        pdf.setFillColor(colors.white)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(margin + 10, y - 10, label)
        y -= 30

    start_page()

    section_label("Patient Biodata")
    pdf.setFillColor(colors.HexColor("#F8FBFC"))
    pdf.setStrokeColor(colors.HexColor("#D9E4EA"))
    biodata_height = 92
    pdf.roundRect(margin, y - biodata_height + 14, page_width - (margin * 2), biodata_height, 10, stroke=1, fill=1)
    pdf.setFillColor(colors.HexColor(TEXT_DARK))
    pdf.setFont("Helvetica", 10)
    rows = [
        (
            f"Name: {_patient_value(patient_details, 'name')}",
            f"Hospital No: {_patient_value(patient_details, 'hospital_number', _patient_value(patient_details, 'patient_id'))}",
        ),
        (
            f"Age: {_patient_value(patient_details, 'age')}",
            f"Gender: {_patient_value(patient_details, 'gender')}",
        ),
        (
            f"Phone: {_patient_value(patient_details, 'phone')}",
            f"Date: {date_text} {time_text}",
        ),
        (
            f"Allergy: {_patient_value(patient_details, 'allergy', 'None recorded')}",
            f"Medical Conditions: {_patient_value(patient_details, 'medical_conditions', 'None recorded')}",
        ),
    ]
    row_y = y - 8
    for left_text, right_text in rows:
        pdf.drawString(margin + 12, row_y, left_text)
        pdf.drawString(margin + 270, row_y, right_text)
        row_y -= 18
    y = y - biodata_height - 18

    section_label("Referral Note")
    note_lines = _wrap_lines(referral_note or "Not recorded", 86)
    note_bottom = 168
    note_height = max(250, y - note_bottom)
    pdf.setFillColor(colors.white)
    pdf.setStrokeColor(colors.HexColor(BRAND_BLUE))
    pdf.roundRect(margin, y - note_height, page_width - (margin * 2), note_height, 10, stroke=1, fill=1)
    text_y = y - 18
    pdf.setFillColor(colors.HexColor(TEXT_DARK))
    pdf.setFont("Helvetica", 11)
    for line in note_lines:
        if text_y < note_bottom + 14:
            _draw_signature(pdf, doctor_id, doctor_name, margin + 4, 118)
            pdf.setFillColor(colors.HexColor(TEXT_DARK))
            pdf.setFont("Helvetica", 9)
            pdf.drawRightString(page_width - margin, 104, f"Issued: {date_text} {time_text}")
            _draw_document_footer(pdf, page_width, margin)
            pdf.showPage()
            start_page()
            section_label("Referral Note Continued")
            note_height = y - note_bottom
            pdf.setFillColor(colors.white)
            pdf.setStrokeColor(colors.HexColor(BRAND_BLUE))
            pdf.roundRect(margin, y - note_height, page_width - (margin * 2), note_height, 10, stroke=1, fill=1)
            text_y = y - 18
            pdf.setFillColor(colors.HexColor(TEXT_DARK))
            pdf.setFont("Helvetica", 11)
        pdf.drawString(margin + 12, text_y, line)
        text_y -= 16

    _draw_signature(pdf, doctor_id, doctor_name, margin + 4, 118)
    pdf.setFillColor(colors.HexColor(TEXT_DARK))
    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(page_width - margin, 104, f"Issued: {date_text} {time_text}")
    _draw_document_footer(pdf, page_width, margin)
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
        medications_text = "\n".join(
            f"{index}. {med['route']}  {med['name']}  {med['dose']}  {med['duration']}"
            for index, med in enumerate(medications, start=1)
        )
    rx_id = uuid4().hex
    filename = f"synmed_prescription_{consultation_id[:8]}_{rx_id[:6]}.pdf"
    file_buffer = _render_pdf(
        filename=filename,
        title="Prescription",
        doctor_id=doctor_id,
        doctor_name=doctor_name,
        patient_details=patient_details,
        diagnosis=diagnosis,
        history=patient_details.get("history", "Not recorded"),
        body_label="Prescription",
        body_text=medications_text,
        date_text=date_text,
        time_text=time_text,
        notes=notes,
        include_history=False,
    )
    asset_path = _relative_asset_path(filename)
    medication_payload = medications or [{"text": line.strip()} for line in medications_text.splitlines() if line.strip()]

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
        "content": _build_content(
            title="Prescription",
            patient_details=patient_details,
            diagnosis=diagnosis,
            history=patient_details.get("history", "Not recorded"),
            body_label="Prescription",
            body_text=medications_text,
            doctor_name=doctor_name,
            date_text=date_text,
            time_text=time_text,
            notes=notes,
        ),
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
    request_id = uuid4().hex
    filename = f"synmed_investigation_{consultation_id[:8]}_{request_id[:6]}.pdf"
    file_buffer = _render_pdf(
        filename=filename,
        title="Investigation Request",
        doctor_id=doctor_id,
        doctor_name=doctor_name,
        patient_details=patient_details,
        diagnosis=diagnosis,
        history=patient_details.get("history", "Not recorded"),
        body_label="Investigation Request",
        body_text=tests_text,
        date_text=date_text,
        time_text=time_text,
        notes=notes,
        include_history=False,
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
        "content": _build_content(
            title="Investigation Request",
            patient_details=patient_details,
            diagnosis=diagnosis,
            history=patient_details.get("history", "Not recorded"),
            body_label="Investigation Request",
            body_text=tests_text,
            doctor_name=doctor_name,
            date_text=date_text,
            time_text=time_text,
            notes=notes,
        ),
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
    history = patient_details.get("history", "Not recorded")
    letter_id = uuid4().hex
    filename = f"synmed_referral_{consultation_id[:8]}_{letter_id[:6]}.pdf"
    file_buffer = _render_pdf(
        filename=filename,
        title="Referral Note",
        doctor_id=doctor_id,
        doctor_name=doctor_name,
        patient_details=patient_details,
        diagnosis=diagnosis,
        history=history,
        body_label="Referral Note",
        body_text=referral_note,
        date_text=date_text,
        time_text=time_text,
        notes=f"Hospital Referred To: {referred_hospital}",
    )
    asset_path = _relative_asset_path(filename)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO clinical_letters (
                letter_id, consultation_id, doctor_id, patient_id, letter_type,
                diagnosis, body_text, target_hospital, notes, created_at, asset_path, asset_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                letter_id,
                consultation_id,
                str(doctor_id),
                str(patient_id),
                "referral",
                diagnosis,
                referral_note,
                referred_hospital,
                history,
                issued_at.isoformat(),
                asset_path,
                "application/pdf",
            ),
        )
        conn.commit()

    return {
        "document_id": letter_id,
        "filename": filename,
        "file": file_buffer,
        "content": _build_content(
            title="Referral Note",
            patient_details=patient_details,
            diagnosis=diagnosis,
            history=history,
            body_label="Referral Note",
            body_text=referral_note,
            doctor_name=doctor_name,
            date_text=date_text,
            time_text=time_text,
            notes=f"Hospital Referred To: {referred_hospital}",
        ),
        "asset_path": asset_path,
        "asset_url": _public_asset_url(filename),
        "asset_type": "application/pdf",
        "created_at": issued_at.isoformat(),
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
    history = patient_details.get("history", "Not recorded")
    letter_id = uuid4().hex
    filename = f"synmed_medical_report_{consultation_id[:8]}_{letter_id[:6]}.pdf"
    file_buffer = _render_medical_report_pdf(
        filename=filename,
        doctor_id=doctor_id,
        doctor_name=doctor_name,
        patient_details=patient_details,
        referral_note=report_note,
        date_text=date_text,
        time_text=time_text,
    )
    asset_path = _relative_asset_path(filename)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO clinical_letters (
                letter_id, consultation_id, doctor_id, patient_id, letter_type,
                diagnosis, body_text, target_hospital, notes, created_at, asset_path, asset_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                letter_id,
                consultation_id,
                str(doctor_id),
                str(patient_id),
                "medical_report",
                diagnosis,
                report_note,
                None,
                history,
                issued_at.isoformat(),
                asset_path,
                "application/pdf",
            ),
        )
        conn.commit()

    return {
        "document_id": letter_id,
        "filename": filename,
        "file": file_buffer,
        "content": _build_content(
            title="Medical Report",
            patient_details=patient_details,
            diagnosis=diagnosis,
            history=history,
            body_label="Referral Note",
            body_text=report_note,
            doctor_name=doctor_name,
            date_text=date_text,
            time_text=time_text,
        ),
        "asset_path": asset_path,
        "asset_url": _public_asset_url(filename),
        "asset_type": "application/pdf",
        "created_at": issued_at.isoformat(),
    }


def regenerate_prescription_document(row, patient_details: dict):
    diagnosis = "N/A"
    medications_text = ""
    try:
        payload = json.loads(row["medication_json"] or "{}")
        diagnosis = payload.get("diagnosis") or "N/A"
        lines = []
        for index, medication in enumerate(payload.get("medications") or [], start=1):
            if isinstance(medication, dict) and {"route", "name", "dose", "duration"}.issubset(set(medication.keys())):
                lines.append(
                    f"{index}. {medication['route']}  {medication['name']}  {medication['dose']}  {medication['duration']}"
                )
            elif isinstance(medication, dict) and medication.get("text"):
                lines.append(f"{index}. {medication['text']}")
            else:
                lines.append(f"{index}. {str(medication)}")
        medications_text = "\n".join(lines)
    except (TypeError, ValueError, json.JSONDecodeError):
        pass

    document = create_prescription_document(
        consultation_id=row["consultation_id"],
        doctor_id=int(row["doctor_id"]),
        patient_id=row["patient_id"],
        patient_details=patient_details,
        diagnosis=diagnosis,
        medications_text=medications_text,
        medications=[],
        notes=row["notes"] or "",
    )
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
    document = create_investigation_document(
        consultation_id=row["consultation_id"],
        doctor_id=int(row["doctor_id"]),
        patient_id=row["patient_id"],
        patient_details=patient_details,
        diagnosis=row["diagnosis"] or "N/A",
        tests_text=row["tests_text"] or "No tests recorded.",
        notes=row["notes"] or "",
    )
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
