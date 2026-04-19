import os
import tempfile
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from database import get_connection, init_db
from handlers.chat import relay_message
from handlers.clinical_documents import (
    handle_document_diagnosis,
    handle_document_duration,
    handle_document_investigation_item,
    handle_document_investigation_next,
    handle_document_items,
    handle_document_medication_name,
    handle_document_medication_next,
    handle_document_medication_route,
    handle_document_medication_dose,
    handle_document_notes,
    handle_document_review,
    start_investigation,
    start_prescription,
)
from synmed_utils.active_chats import active_chats, last_consultation, start_chat
from synmed_utils.doctor_profiles import doctor_profiles


def make_message(text=""):
    return SimpleNamespace(text=text, reply_text=AsyncMock())


def make_update(user_id, text=""):
    return SimpleNamespace(
        message=make_message(text),
        effective_user=SimpleNamespace(id=user_id),
    )


def make_callback_update(user_id, data):
    message = SimpleNamespace(
        reply_text=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
    )
    callback_query = SimpleNamespace(
        data=data,
        from_user=SimpleNamespace(id=user_id),
        message=message,
        answer=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
    )
    return SimpleNamespace(
        callback_query=callback_query,
        effective_user=SimpleNamespace(id=user_id),
    )


def make_context(user_data=None):
    return SimpleNamespace(
        user_data=user_data or {},
        bot=SimpleNamespace(
            send_document=AsyncMock(),
            send_message=AsyncMock(),
            send_chat_action=AsyncMock(),
        ),
    )


class TestClinicalDocuments(IsolatedAsyncioTestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        os.environ["DATABASE_PATH"] = self.db_path
        init_db()
        active_chats.clear()
        last_consultation.clear()
        doctor_profiles.clear()
        os.environ.pop("SYNMED_MOTTO", None)
        os.environ.pop("SYNMED_LOGO_PATH", None)

    def tearDown(self):
        os.environ.pop("DATABASE_PATH", None)
        os.environ.pop("SYNMED_MOTTO", None)
        os.environ.pop("SYNMED_LOGO_PATH", None)
        try:
            os.remove(self.db_path)
        except FileNotFoundError:
            pass
        except PermissionError:
            pass

    async def test_prescription_flow_sends_downloadable_pdf_and_persists_it(self):
        doctor_id = 501
        patient_id = 601
        patient_details = {
            "name": "Ada Lovelace",
            "age": "31",
            "gender": "Female",
            "history": "Headache",
        }
        doctor_profiles[doctor_id] = {
            "name": "Mensah",
            "specialty": "General Medicine",
            "experience": "7",
            "verified": True,
        }
        start_chat(patient_id, doctor_id, patient_details)

        context = make_context()

        with patch("handlers.clinical_documents.is_verified", return_value=True):
            start_result = await start_prescription(make_update(doctor_id), context)

        self.assertEqual(start_result, 6)

        diagnosis_result = await handle_document_diagnosis(
            make_update(doctor_id, "Malaria"), context
        )
        self.assertEqual(diagnosis_result, 9)

        route_result = await handle_document_medication_route(
            make_update(doctor_id, "Tablet / Oral"), context
        )
        self.assertEqual(route_result, 10)

        name_result = await handle_document_medication_name(
            make_update(doctor_id, "Artemether-lumefantrine"), context
        )
        self.assertEqual(name_result, 11)

        dose_result = await handle_document_medication_dose(
            make_update(doctor_id, "80/480mg twice daily"), context
        )
        self.assertEqual(dose_result, 12)

        duration_result = await handle_document_duration(
            make_update(doctor_id, "3 days"), context
        )
        self.assertEqual(duration_result, 13)

        next_result = await handle_document_medication_next(
            make_callback_update(doctor_id, "doc_med:done"), context
        )
        self.assertEqual(next_result, 8)

        notes_result = await handle_document_notes(
            make_update(doctor_id, "Take after meals"), context
        )
        self.assertEqual(notes_result, 14)

        end_result = await handle_document_review(
            make_callback_update(doctor_id, "doc_review:send"),
            context,
        )
        self.assertEqual(end_result, -1)

        context.bot.send_document.assert_awaited_once()
        send_kwargs = context.bot.send_document.await_args.kwargs
        self.assertEqual(send_kwargs["chat_id"], patient_id)
        self.assertIn("synmed_prescription_", send_kwargs["filename"])
        self.assertTrue(send_kwargs["filename"].endswith(".pdf"))
        self.assertTrue(send_kwargs["document"].getvalue().startswith(b"%PDF"))

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT consultation_id, medication_json, notes, is_latest FROM prescriptions"
            )
            row = cursor.fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["consultation_id"], last_consultation[doctor_id]["consultation_id"])
        self.assertEqual(row["notes"], "Take after meals")
        self.assertEqual(row["is_latest"], 1)

    async def test_prescription_review_allows_editing_before_send(self):
        doctor_id = 701
        patient_id = 801
        start_chat(patient_id, doctor_id, {"name": "Ada", "age": "31", "gender": "Female"})
        context = make_context(
            {
                "clinical_document_draft": {
                    "type": "prescription",
                    "consultation_id": "consult-123",
                    "patient_id": patient_id,
                    "patient_details": {"name": "Ada", "age": "31", "gender": "Female"},
                    "doctor_id": doctor_id,
                    "diagnosis": "Old diagnosis",
                    "medications": [
                        {
                            "route": "Tablet / Oral",
                            "name": "Paracetamol",
                            "dose": "500mg twice daily",
                            "duration": "3 days",
                        }
                    ],
                    "notes": "Old notes",
                }
            }
        )

        result = await handle_document_review(make_update(doctor_id, "edit diagnosis"), context)

        self.assertEqual(result, 6)
        self.assertEqual(
            context.user_data["clinical_document_draft"]["diagnosis"],
            "Old diagnosis",
        )

    async def test_draft_messages_are_not_relayed_to_patient(self):
        doctor_id = 501
        patient_id = 601
        start_chat(patient_id, doctor_id, {"name": "Ada"})

        context = make_context(
            {
                "clinical_document_draft": {
                    "type": "prescription",
                    "consultation_id": "abc123",
                }
            }
        )

        await relay_message(make_update(doctor_id, "Draft diagnosis"), context)

        context.bot.send_chat_action.assert_not_awaited()
        context.bot.send_message.assert_not_awaited()

    async def test_investigation_flow_is_structured_and_reviewable(self):
        doctor_id = 901
        patient_id = 902
        patient_details = {
            "name": "Tolu",
            "age": "41",
            "gender": "Male",
            "history": "Back pain",
        }
        doctor_profiles[doctor_id] = {
            "name": "Adebayo",
            "specialty": "Internal Medicine",
            "experience": "11",
            "verified": True,
        }
        start_chat(patient_id, doctor_id, patient_details)

        context = make_context()

        with patch("handlers.clinical_documents.is_verified", return_value=True):
            start_result = await start_investigation(make_update(doctor_id), context)

        self.assertEqual(start_result, 6)

        diagnosis_result = await handle_document_diagnosis(
            make_update(doctor_id, "Rule out renal pathology"), context
        )
        self.assertEqual(diagnosis_result, 15)

        item_result = await handle_document_investigation_item(
            make_update(doctor_id, "Urinalysis"), context
        )
        self.assertEqual(item_result, 16)

        next_result = await handle_document_investigation_next(
            make_callback_update(doctor_id, "doc_inv:add"), context
        )
        self.assertEqual(next_result, 15)

        second_item_result = await handle_document_investigation_item(
            make_update(doctor_id, "Renal ultrasound"), context
        )
        self.assertEqual(second_item_result, 16)

        done_result = await handle_document_investigation_next(
            make_callback_update(doctor_id, "doc_inv:done"), context
        )
        self.assertEqual(done_result, 8)

        notes_result = await handle_document_notes(
            make_update(doctor_id, "Kindly perform within 48 hours"), context
        )
        self.assertEqual(notes_result, 14)

        review_result = await handle_document_review(
            make_callback_update(doctor_id, "doc_review:edit investigations"),
            context,
        )
        self.assertEqual(review_result, 15)
        self.assertEqual(context.user_data["clinical_document_draft"]["investigations"], [])
