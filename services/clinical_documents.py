import json
import os
import textwrap
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont

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
BRAND_BLUE = "#045B76"
BRAND_GOLD = "#F0B24D"
BRAND_DARK = "#12212A"
CARD_FILL = "#F4F8FA"
META_FILL = "#E8F0F4"
FRAME_FILL = "#FBFDFC"
TEXT_DARK = "#20313A"
TEXT_MUTED = "#586972"
CANVAS_WIDTH = 820


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


def _font(size: int, *, bold: bool = False, italic: bool = False):
    font_candidates = []
    if bold and italic:
        font_candidates.extend(["arialbi.ttf", "DejaVuSans-BoldOblique.ttf"])
    elif bold:
        font_candidates.extend(["arialbd.ttf", "DejaVuSans-Bold.ttf"])
    elif italic:
        font_candidates.extend(["ariali.ttf", "DejaVuSans-Oblique.ttf"])
    else:
        font_candidates.extend(["arial.ttf", "DejaVuSans.ttf"])

    for candidate in font_candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


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
) -> str:
    lines = [
        title,
        "",
        "Patient Biodata",
        f"Name: {_patient_line(patient_details, 'name')}",
        f"Age: {_patient_line(patient_details, 'age')}",
        f"Gender: {_patient_line(patient_details, 'gender')}",
        "",
        f"Diagnosis: {diagnosis}",
        "",
        items_label,
        items_text,
        "",
        f"Prescriber: {doctor_name}",
        f"Date: {date_text}",
        f"Time: {time_text}",
    ]
    if notes:
        lines.extend(["", "Notes", notes])
    return "\n".join(lines)


def _build_document_payload(
    *,
    title: str,
    consultation_id: str,
    patient_details: dict,
    diagnosis: str,
    items_label: str,
    items_text: str,
    doctor_name: str,
    notes: str,
    date_text: str,
    time_text: str,
):
    hospital_number = (
        patient_details.get("hospital_number")
        or patient_details.get("hospital_no")
        or patient_details.get("patient_id")
        or "N/A"
    )
    return {
        "title": title,
        "consultation_id": consultation_id,
        "hospital_number": str(hospital_number),
        "patient_details": patient_details,
        "diagnosis": diagnosis,
        "items_label": items_label,
        "items": [line.strip() for line in items_text.splitlines() if line.strip()],
        "doctor_name": doctor_name,
        "notes": notes,
        "date_text": date_text,
        "time_text": time_text,
    }


def _format_prescription_medications(medications: list[dict]) -> str:
    return "\n".join(
        f"{index}. {med['route']}  {med['name']}  {med['dose']}  {med['duration']}"
        for index, med in enumerate(medications, start=1)
    )


def _wrap_line(text: str, width: int) -> list[str]:
    text = text.strip()
    if not text:
        return [""]
    return textwrap.wrap(text, width=width) or [text]


def _measure_multiline(lines: list[str], font, line_height: int) -> int:
    return max(1, len(lines)) * line_height


def _save_document_image(filename: str, payload: dict) -> BytesIO:
    GENERATED_DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    path = GENERATED_DOCUMENTS_DIR / filename

    margin = 48
    header_height = 182
    section_gap = 24
    title_font = _font(48, bold=True)
    document_title_font = _font(24, bold=True)
    heading_font = _font(22, bold=True)
    subheading_font = _font(16, bold=True)
    body_font = _font(17)
    small_font = _font(14)
    italic_font = _font(14, italic=True)
    line_height = 28
    wrap_width = 42
    is_prescription = payload["title"].lower() == "prescription"
    section_title = "Prescription" if is_prescription else "Requested Tests"
    accent_label = "" if is_prescription else "Lab"
    accent_font_size = 34
    items_fill = "#FFF7E7" if is_prescription else "#EEF8FA"
    items_outline = BRAND_GOLD if is_prescription else BRAND_BLUE
    divider_color = "#E6CF94" if is_prescription else "#9FCFDD"
    header_tint = "#D9EDF4" if is_prescription else "#E0F5F6"
    footer_caption = "SynMed Prescription Sheet" if is_prescription else "SynMed Investigation Sheet"

    diagnosis_lines = _wrap_line(payload["diagnosis"], wrap_width)
    notes_lines = _wrap_line(payload["notes"], wrap_width) if payload["notes"] else []
    item_lines = []
    for item in payload["items"] or ["No items provided."]:
        item_lines.extend(_wrap_line(item, wrap_width - 2))

    patient_name_lines = _wrap_line(_patient_line(payload["patient_details"], "name"), 18)
    age_value = _patient_line(payload["patient_details"], "age")
    gender_value = _patient_line(payload["patient_details"], "gender")
    hospital_number_value = payload["hospital_number"]

    body_height = (
        118
        + max(_measure_multiline(patient_name_lines, body_font, line_height), 56)
        + _measure_multiline(diagnosis_lines, body_font, line_height)
        + _measure_multiline(item_lines, body_font, line_height)
        + (_measure_multiline(notes_lines, body_font, line_height) + 64 if notes_lines else 0)
        + 220
    )
    image_height = max(header_height + body_height + 260, int(CANVAS_WIDTH * 1.72))

    image = Image.new("RGB", (CANVAS_WIDTH, image_height), "white")
    draw = ImageDraw.Draw(image)

    draw.rectangle((18, 18, CANVAS_WIDTH - 18, image_height - 18), outline=BRAND_GOLD, width=2)
    draw.rectangle((28, 28, CANVAS_WIDTH - 28, image_height - 28), fill=FRAME_FILL, outline="#D8E4E9", width=2)
    draw.rectangle((0, 0, CANVAS_WIDTH, header_height), fill=BRAND_DARK)
    draw.rectangle((0, header_height - 10, CANVAS_WIDTH, header_height), fill=BRAND_BLUE)

    logo = _logo_path()
    if logo:
      try:
        logo_image = Image.open(logo).convert("RGBA")
        logo_image.thumbnail((92, 92))
        image.paste(logo_image, (margin, 24), logo_image)
      except Exception:
        pass

    header_title = "SynMed Telehealth"
    header_title_width = draw.textlength(header_title, font=title_font)
    draw.text(
        ((CANVAS_WIDTH - header_title_width) / 2, 24),
        header_title,
        fill="white",
        font=title_font,
    )
    motto = _motto_text()
    if motto:
        motto_width = draw.textlength(motto, font=italic_font)
        draw.text(
            ((CANVAS_WIDTH - motto_width) / 2, 82),
            motto,
            fill=BRAND_GOLD,
            font=italic_font,
        )
    document_title = payload["title"].upper()
    document_title_width = draw.textlength(document_title, font=document_title_font)
    draw.text(
        ((CANVAS_WIDTH - document_title_width) / 2, 112),
        document_title,
        fill=header_tint,
        font=document_title_font,
    )

    y = header_height + 28

    meta_top = y
    meta_height = 76
    meta_gap = 14
    meta_width = CANVAS_WIDTH - (margin * 2)
    meta_card_width = int((meta_width - (meta_gap * 2)) / 3)
    meta_items = [
        ("Document", payload["title"]),
        ("Date", payload["date_text"]),
        ("Hospital No.", payload["hospital_number"]),
    ]

    for index, (label, value) in enumerate(meta_items):
        x1 = margin + (index * (meta_card_width + meta_gap))
        x2 = x1 + meta_card_width
        draw.rounded_rectangle((x1, meta_top, x2, meta_top + meta_height), radius=16, fill=META_FILL)
        draw.text((x1 + 16, meta_top + 12), label.upper(), fill=BRAND_BLUE, font=small_font)
        draw.text((x1 + 16, meta_top + 40), value, fill=TEXT_DARK, font=subheading_font)
    y += meta_height + 18

    def section(title: str):
        nonlocal y
        draw.rounded_rectangle((margin, y, margin + 260, y + 34), radius=12, fill=BRAND_BLUE)
        draw.text((margin + 16, y + 7), title, fill="white", font=subheading_font)
        y += 46

    section("Patient Biodata")
    biodata_height = max(122, 78 + _measure_multiline(patient_name_lines, body_font, line_height))
    draw.rounded_rectangle((margin, y, CANVAS_WIDTH - margin, y + biodata_height), radius=18, fill=CARD_FILL)
    left_col_x = margin + 24
    right_col_x = margin + ((CANVAS_WIDTH - (margin * 2)) // 2) + 10
    draw.text((left_col_x, y + 16), "Patient Name", fill=TEXT_MUTED, font=small_font)
    name_y = y + 40
    for line in patient_name_lines:
        draw.text((left_col_x, name_y), line, fill=TEXT_DARK, font=body_font)
        name_y += line_height

    draw.text((right_col_x, y + 16), "Hospital Number", fill=TEXT_MUTED, font=small_font)
    draw.text((right_col_x, y + 40), hospital_number_value, fill=TEXT_DARK, font=body_font)
    draw.text((right_col_x, y + 72), "Age", fill=TEXT_MUTED, font=small_font)
    draw.text((right_col_x + 60, y + 72), age_value, fill=TEXT_DARK, font=body_font)
    draw.text((right_col_x + 140, y + 72), "Gender", fill=TEXT_MUTED, font=small_font)
    draw.text((right_col_x + 220, y + 72), gender_value, fill=TEXT_DARK, font=body_font)
    y += biodata_height + section_gap

    section("Diagnosis")
    diagnosis_height = 30 + (_measure_multiline(diagnosis_lines, body_font, line_height))
    draw.rounded_rectangle((margin, y, CANVAS_WIDTH - margin, y + diagnosis_height), radius=18, fill=CARD_FILL)
    text_y = y + 16
    for line in diagnosis_lines:
        draw.text((margin + 24, text_y), line, fill=TEXT_DARK, font=body_font)
        text_y += line_height
    y += diagnosis_height + section_gap

    section(payload["items_label"])
    items_height = 76 + (_measure_multiline(item_lines, body_font, line_height))
    draw.rounded_rectangle(
        (margin, y, CANVAS_WIDTH - margin, y + items_height),
        radius=22,
        fill=items_fill,
        outline=items_outline,
        width=3,
    )
    if accent_label:
        accent_font = _font(accent_font_size, bold=True, italic=True)
        draw.text((margin + 22, y + 18), accent_label, fill=items_outline, font=accent_font)
        title_x = margin + 112
    else:
        title_x = margin + 24
    draw.text((title_x, y + 22), section_title, fill=BRAND_BLUE, font=heading_font)
    draw.line((margin + 24, y + 62, CANVAS_WIDTH - margin - 24, y + 62), fill=divider_color, width=2)
    text_y = y + 82
    for line in item_lines:
        draw.text((margin + 24, text_y), line, fill=TEXT_DARK, font=body_font)
        text_y += line_height
    y += items_height + section_gap

    if notes_lines:
        section("Notes")
        notes_height = 42 + (_measure_multiline(notes_lines, body_font, line_height))
        draw.rounded_rectangle((margin, y, CANVAS_WIDTH - margin, y + notes_height), radius=18, fill=CARD_FILL)
        text_y = y + 20
        for line in notes_lines:
            draw.text((margin + 24, text_y), line, fill=TEXT_DARK, font=body_font)
            text_y += line_height
        y += notes_height + section_gap

    footer_top = y + 18
    footer_height = 154
    draw.rounded_rectangle(
        (margin, footer_top, CANVAS_WIDTH - margin, footer_top + footer_height),
        radius=20,
        fill="#F7FAFC",
        outline="#D4E1E8",
        width=2,
    )

    signature_y = footer_top + 42
    draw.line((margin + 24, signature_y, margin + 284, signature_y), fill="#C7D6DE", width=2)
    draw.line((CANVAS_WIDTH - margin - 284, signature_y, CANVAS_WIDTH - margin - 24, signature_y), fill="#C7D6DE", width=2)
    draw.text((margin + 24, signature_y + 12), payload["doctor_name"], fill=TEXT_DARK, font=subheading_font)
    draw.text((margin + 24, signature_y + 42), "Prescriber Signature / Name", fill=TEXT_MUTED, font=small_font)
    date_width = draw.textlength(payload["date_text"], font=subheading_font)
    draw.text((CANVAS_WIDTH - margin - 24 - date_width, signature_y + 12), payload["date_text"], fill=TEXT_DARK, font=subheading_font)
    label_width = draw.textlength("Issue Date", font=small_font)
    draw.text((CANVAS_WIDTH - margin - 24 - label_width, signature_y + 42), "Issue Date", fill=TEXT_MUTED, font=small_font)
    draw.text((margin + 24, footer_top + 100), footer_caption, fill=BRAND_BLUE, font=small_font)
    draw.text((margin + 24, footer_top + 122), "Generated by SynMed Telehealth", fill=TEXT_MUTED, font=italic_font)

    image.save(path, format="PNG")
    buffer = BytesIO(path.read_bytes())
    buffer.name = filename
    buffer.seek(0)
    return buffer


def _relative_asset_path(filename: str) -> str:
    return f"generated_documents/{filename}"


def _public_asset_url(filename: str) -> str:
    return f"/generated-documents/{filename}"


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
        items_label="Medications",
        items_text=medications_text,
        doctor_name=doctor_name,
        notes=notes,
        date_text=date_text,
        time_text=time_text,
    )
    payload = _build_document_payload(
        title="Prescription",
        consultation_id=consultation_id,
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
    filename = f"synmed_prescription_{consultation_id[:8]}_{rx_id[:6]}.png"
    image_buffer = _save_document_image(filename, payload)
    asset_path = _relative_asset_path(filename)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE prescriptions SET is_latest = 0 WHERE consultation_id = ?",
            (consultation_id,),
        )
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
                json.dumps(
                    {
                        "diagnosis": diagnosis,
                        "medications": medication_payload,
                    }
                ),
                notes,
                1,
                issued_at.isoformat(),
                asset_path,
                "image/png",
            ),
        )
        conn.commit()

    return {
        "document_id": rx_id,
        "filename": filename,
        "file": image_buffer,
        "content": content,
        "asset_path": asset_path,
        "asset_url": _public_asset_url(filename),
        "asset_type": "image/png",
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
    payload = _build_document_payload(
        title="Investigation Request",
        consultation_id=consultation_id,
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
    filename = f"synmed_investigation_{consultation_id[:8]}_{request_id[:6]}.png"
    image_buffer = _save_document_image(filename, payload)
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
                "image/png",
            ),
        )
        conn.commit()

    return {
        "document_id": request_id,
        "filename": filename,
        "file": image_buffer,
        "content": content,
        "asset_path": asset_path,
        "asset_url": _public_asset_url(filename),
        "asset_type": "image/png",
    }
