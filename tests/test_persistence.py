import os
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone

from database import init_db
from services.admin_audit import get_recent_admin_actions, log_admin_action
from services.analytics import get_admin_analytics
from services.backups import create_database_backup
from services.consultation_records import (
    export_consultation_file,
    get_consultation_timeline,
    get_patient_history,
    get_patient_history_by_identifier,
    log_consultation_event,
    log_consultation_message,
    set_doctor_private_notes,
    start_consultation_record,
)
from services.clinical_documents import create_investigation_document, create_prescription_document
from services.followups import (
    get_due_follow_up_reminders,
    get_upcoming_follow_ups,
    mark_follow_up_reminded,
    schedule_follow_up,
)
from services.patient_records import (
    get_patient_by_identifier,
    register_patient,
    search_patient_records,
    update_patient_record,
)
from synmed_utils.doctor_profiles import create_or_update_profile, doctor_profiles
from synmed_utils.active_chats import active_chats, last_consultation, start_chat
import synmed_utils.doctor_registry as doctor_registry
from synmed_utils.pending_doctors import pending_doctors
import synmed_utils.support_registry as support_registry


class TestPersistenceStores(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        os.environ["DATABASE_PATH"] = self.db_path
        init_db()

    def tearDown(self):
        os.environ.pop("DATABASE_PATH", None)
        try:
            os.remove(self.db_path)
        except FileNotFoundError:
            pass
        except PermissionError:
            pass

    def test_doctor_profile_is_persisted_and_updated(self):
        create_or_update_profile(
            2001,
            {
                "name": "Dr. Ada",
                "specialty": "Cardiology",
                "experience": "9",
                "username": "drada",
                "verified": False,
            },
        )
        create_or_update_profile(2001, {"verified": True, "license_id": "MDCN-123"})

        profile = doctor_profiles.get(2001)
        self.assertEqual(profile["name"], "Dr. Ada")
        self.assertEqual(profile["specialty"], "Cardiology")
        self.assertEqual(profile["license_id"], "MDCN-123")
        self.assertTrue(profile["verified"])

    def test_pending_doctor_request_is_persisted_and_removed(self):
        pending_doctors[3001] = {
            "name": "Dr. Tolu",
            "specialty": "Neurology",
            "experience": "6",
            "license_id": "MDCN-777",
            "username": "drtolu",
            "file_id": "file-123",
            "file_type": "document",
        }

        self.assertIn(3001, pending_doctors)
        self.assertEqual(len(pending_doctors), 1)
        self.assertEqual(pending_doctors.get(3001)["license_id"], "MDCN-777")

        removed = pending_doctors.pop(3001)
        self.assertEqual(removed["name"], "Dr. Tolu")
        self.assertNotIn(3001, pending_doctors)
        self.assertEqual(len(pending_doctors), 0)

    def test_patient_records_assign_progressive_hospital_numbers_and_update(self):
        first = register_patient(
            telegram_id=4001,
            name="Ada",
            age="29",
            gender="Female",
            phone="08010000001",
            address="Ikeja",
            allergy="None",
        )
        second = register_patient(
            telegram_id=4002,
            name="Tolu",
            age="41",
            gender="Male",
            phone="08010000002",
            address="Yaba",
            allergy="Dust",
        )

        self.assertEqual(first["hospital_number"], "SM0001")
        self.assertEqual(second["hospital_number"], "SM0002")

        updated = update_patient_record("SM0002", "address", "Lekki")
        self.assertEqual(updated["address"], "Lekki")
        self.assertEqual(get_patient_by_identifier("08010000002")["hospital_number"], "SM0002")

    def test_consultation_export_contains_biodata_and_transcript(self):
        patient = register_patient(
            telegram_id=5001,
            name="Ada",
            age="29",
            gender="Female",
            phone="08010000003",
            address="Ikeja",
            allergy="Peanuts",
        )
        consultation_id = "consult-legal-1"
        start_consultation_record(
            consultation_id,
            patient_record=patient,
            doctor_id=9001,
            summary="Symptoms / History: Headache",
        )
        log_consultation_message(
            consultation_id,
            sender_id=5001,
            sender_role="patient",
            message_text="I have had a headache for 2 days.",
        )
        log_consultation_message(
            consultation_id,
            sender_id=9001,
            sender_role="doctor",
            message_text="Do you have fever as well?",
        )

        export = export_consultation_file("SM0001")

        self.assertIsNotNone(export)
        content = export["file"].getvalue().decode("utf-8")
        self.assertIn("Hospital Number: SM0001", content)
        self.assertIn("Name: Ada", content)
        self.assertIn("I have had a headache for 2 days.", content)
        self.assertIn("Do you have fever as well?", content)

    def test_patient_search_history_and_private_notes_are_persisted(self):
        patient = register_patient(
            telegram_id=6001,
            name="Ada Lovelace",
            age="29",
            gender="Female",
            phone="08010000011",
            address="Ikeja",
            allergy="Peanuts",
        )
        consultation_id = "consult-history-1"
        start_consultation_record(
            consultation_id,
            patient_record=patient,
            doctor_id=7001,
            summary="Symptoms / History: Migraine",
        )
        set_doctor_private_notes(consultation_id, "Possible migraine with aura.")

        matches = search_patient_records("Ada")
        history = get_patient_history(6001)
        export = export_consultation_file(consultation_id)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["hospital_number"], "SM0001")
        self.assertIsNotNone(history)
        self.assertEqual(history["patient_id"], "SM0001")
        self.assertEqual(history["consultations"][0]["doctor_private_notes"], "Possible migraine with aura.")
        self.assertIn("Possible migraine with aura.", export["file"].getvalue().decode("utf-8"))

    def test_admin_audit_log_persists_recent_actions(self):
        log_admin_action(
            admin_id=9001,
            action="edit_patient_record",
            target_type="patient",
            target_id="SM0001",
            details="Updated allergy field",
        )
        log_admin_action(
            admin_id=9001,
            action="export_consultation",
            target_type="consultation",
            target_id="consult-abc",
            details="Downloaded transcript",
        )

        entries = get_recent_admin_actions()

        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["action"], "export_consultation")
        self.assertEqual(entries[1]["target_id"], "SM0001")

    def test_doctor_history_view_includes_previous_diagnoses_and_investigations(self):
        patient = register_patient(
            telegram_id=7001,
            name="Musa",
            age="35",
            gender="Male",
            phone="08010000021",
            address="Abuja",
            allergy="None",
        )
        consultation_id = "consult-history-2"
        start_consultation_record(
            consultation_id,
            patient_record=patient,
            doctor_id=9101,
            summary="Symptoms / History: Recurrent cough",
        )
        create_prescription_document(
            consultation_id=consultation_id,
            doctor_id=9101,
            patient_id=patient["hospital_number"],
            patient_details=patient,
            diagnosis="Upper respiratory tract infection",
            medications=[{"route": "PO", "name": "Amoxicillin", "dose": "500mg", "duration": "5 days"}],
            notes="Take after meals",
        )
        create_investigation_document(
            consultation_id=consultation_id,
            doctor_id=9101,
            patient_id=patient["hospital_number"],
            patient_details=patient,
            diagnosis="Upper respiratory tract infection",
            tests_text="Chest X-ray",
            notes="Rule out pneumonia",
        )

        history = get_patient_history_by_identifier("SM0001")

        self.assertIsNotNone(history)
        self.assertEqual(history["prescriptions"][0]["diagnosis"], "Upper respiratory tract infection")
        self.assertEqual(history["investigations"][0]["diagnosis"], "Upper respiratory tract infection")
        self.assertIn("Chest X-ray", history["investigations"][0]["tests_text"])

    def test_followup_timeline_and_analytics_are_persisted(self):
        patient = register_patient(
            telegram_id=8001,
            name="Amina",
            age="31",
            gender="Female",
            phone="08010000031",
            address="Kaduna",
            allergy="Penicillin",
        )
        consultation_id = "consult-ops-1"
        start_consultation_record(
            consultation_id,
            patient_record=patient,
            doctor_id=9201,
            summary="Symptoms / History: Chest discomfort",
        )
        appointment = schedule_follow_up(
            consultation_id=consultation_id,
            patient_id=patient["hospital_number"],
            doctor_id=9201,
            scheduled_for="2026-04-01 10:00",
            notes="Review ECG result",
        )
        log_consultation_event(
            consultation_id,
            event_type="followup_scheduled",
            actor_id="9201",
            details="2026-04-01 10:00 | Review ECG result",
        )

        followups = get_upcoming_follow_ups()
        timeline = get_consultation_timeline(consultation_id)
        analytics = get_admin_analytics()

        self.assertEqual(appointment["status"], "scheduled")
        self.assertEqual(len(followups), 1)
        self.assertEqual(followups[0]["patient_id"], "SM0001")
        self.assertIsNotNone(timeline)
        self.assertEqual(timeline["events"][0]["event_type"], "consultation_started")
        self.assertEqual(timeline["events"][-1]["event_type"], "followup_scheduled")
        self.assertEqual(analytics["patients"], 1)
        self.assertEqual(analytics["consultations"], 1)
        self.assertEqual(analytics["follow_ups"], 1)

    def test_database_backup_creates_snapshot_file(self):
        patient = register_patient(
            telegram_id=8101,
            name="Backup Test",
            age="40",
            gender="Male",
            phone="08010000041",
            address="Lagos",
            allergy="None",
        )

        backup = create_database_backup()

        self.assertEqual(patient["hospital_number"], "SM0001")
        self.assertTrue(Path(backup["path"]).exists())
        self.assertTrue(backup["filename"].startswith("synmed_backup_"))
        Path(backup["path"]).unlink(missing_ok=True)

    def test_due_followup_reminders_can_be_selected_and_marked(self):
        schedule_follow_up(
            consultation_id="consult-reminder-1",
            patient_id="SM0001",
            doctor_id=9301,
            scheduled_for="2026-03-25 10:00",
            notes="Follow-up review",
        )

        due = get_due_follow_up_reminders(
            now=datetime(2026, 3, 24, 12, 0, tzinfo=timezone.utc)
        )

        self.assertEqual(len(due), 1)
        mark_follow_up_reminded(due[0]["appointment_id"])
        refreshed = get_upcoming_follow_ups()
        self.assertEqual(refreshed[0]["status"], "reminded")

    def test_runtime_consultation_state_can_be_restored_after_restart(self):
        doctor_registry.clear_doctor_runtime_state()
        active_chats.clear()
        last_consultation.clear()

        patient_details = {
            "hospital_number": "SM0001",
            "name": "Ada",
            "age": "29",
            "gender": "Female",
            "phone": "08010000001",
            "address": "Ikeja",
            "allergy": "None",
            "history": "Headache",
        }
        doctor_registry.set_doctor_available(9001)
        doctor_registry.queue_patient(5001, patient_details)
        consultation_id = start_chat(5001, 9001, patient_details)
        doctor_registry.set_doctor_busy(9001)

        doctor_registry.clear_doctor_runtime_state()
        active_chats.clear()
        last_consultation.clear()

        doctor_registry.restore_runtime_state()
        from synmed_utils.active_chats import restore_runtime_state as restore_active_chats
        restore_active_chats()

        self.assertEqual(doctor_registry.busy_doctors, {9001})
        self.assertIn(5001, active_chats)
        self.assertEqual(active_chats[5001], 9001)
        self.assertEqual(last_consultation[5001]["consultation_id"], consultation_id)

    def test_runtime_support_state_can_be_restored_after_restart(self):
        support_registry.clear_runtime_state()
        support_registry.set_support_available(8001)
        support_registry.queue_support_user(6001)
        support_registry.start_support_chat(6002, 8001)

        support_registry.clear_runtime_state()
        support_registry.restore_runtime_state()

        self.assertIn(8001, support_registry.busy_support_agents)
        self.assertIn(6001, support_registry.waiting_support_users)
        self.assertEqual(support_registry.get_support_partner(6002), 8001)
