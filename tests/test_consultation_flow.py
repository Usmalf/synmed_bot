import os
import tempfile
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from database import init_db
from bot import route_priority_text_inputs
from handlers.doctor import doctor_on
from handlers.end_chat import end_chat_confirm_handler, end_chat_handler
from handlers.followups import (
    FOLLOWUP_DATE_STATE,
    FOLLOWUP_DRAFT_KEY,
    FOLLOWUP_NOTES_STATE,
    FOLLOWUP_STATE_KEY,
    FOLLOWUP_TIME_STATE,
    followup_handler,
    handle_followup_date_pick,
    handle_followup_input,
    handle_followup_navigation,
)
from handlers.admin_ops import send_due_followup_reminders
from handlers.customer_care import customer_care_callback, customer_care_handler
from handlers.patient import (
    PAYMENT_PENDING,
    REG_ALLERGY,
    REG_EMAIL,
    REG_NAME,
    RETURN_EMAIL,
    handle_patient_intake,
    handle_payment_callback,
)
from services.followups import get_upcoming_follow_ups, schedule_follow_up
from services.patient_records import get_patient_by_identifier, register_patient
import synmed_utils.doctor_registry as registry
from synmed_utils.active_chats import active_chats, last_consultation, start_chat
from synmed_utils.doctor_profiles import doctor_profiles
from synmed_utils.support_registry import (
    approved_support_agents,
    available_support_agents,
    busy_support_agents,
    pending_support_requests,
    support_chats,
    support_profiles,
    waiting_support_users,
)
from handlers.patient import SYMPTOMS


def make_message(text=""):
    return SimpleNamespace(text=text, reply_text=AsyncMock())


def make_update(user_id, text="", chat_type="private"):
    message = make_message(text)
    return SimpleNamespace(
        message=message,
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(type=chat_type),
    )


def make_context(user_data=None):
    return SimpleNamespace(
        user_data=user_data or {},
        bot=SimpleNamespace(send_message=AsyncMock()),
        bot_data={},
    )


class TestConsultationFlow(IsolatedAsyncioTestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        os.environ["DATABASE_PATH"] = self.db_path
        init_db()
        registry.available_doctors.clear()
        registry.busy_doctors.clear()
        registry.waiting_patients.clear()
        registry.pending_patient_details.clear()
        active_chats.clear()
        last_consultation.clear()
        doctor_profiles.clear()
        approved_support_agents.clear()
        available_support_agents.clear()
        busy_support_agents.clear()
        waiting_support_users.clear()
        pending_support_requests.clear()
        support_profiles.clear()
        support_chats.clear()

    def tearDown(self):
        os.environ.pop("DATABASE_PATH", None)
        try:
            os.remove(self.db_path)
        except FileNotFoundError:
            pass
        except PermissionError:
            pass

    async def test_patient_is_queued_with_intake_details_when_no_doctor_is_online(self):
        patient_id = 101
        patient = register_patient(
            telegram_id=patient_id,
            name="Ada",
            age="29",
            gender="Female",
            phone="08012345678",
            address="Ikeja",
            allergy="Peanuts",
        )
        update = make_update(patient_id, text="Headache and fever")
        context = make_context({
            "patient_record": patient,
            "patient_flow_state": SYMPTOMS,
        })

        result = await handle_patient_intake(update, context)

        self.assertIsNone(result)
        self.assertEqual(registry.waiting_patients, [patient_id])
        self.assertEqual(
            registry.pending_patient_details[patient_id],
            {
                "hospital_number": "SM0001",
                "name": "Ada",
                "age": "29",
                "gender": "Female",
                "phone": "08012345678",
                "address": "Ikeja",
                "allergy": "Peanuts",
                "history": "Headache and fever",
                "telegram_id": patient_id,
                "emergency_flag": False,
                "emergency_matches": "",
            },
        )
        update.message.reply_text.assert_awaited_once()

    async def test_new_patient_is_not_registered_before_payment_success(self):
        update = make_update(101, text="ada@example.com")
        context = make_context(
            {
                "reg_name": "Ada",
                "reg_age": "29",
                "reg_gender": "Female",
                "reg_phone": "08012345678",
                "reg_address": "Ikeja",
                "reg_allergy": "Peanuts",
                "patient_flow_state": REG_EMAIL,
            }
        )

        with patch("handlers.patient.initialize_transaction", new=AsyncMock()) as mocked_init:
            mocked_init.return_value = {
                "authorization_url": "https://paystack.test/pay/123",
                "access_code": "code-123",
            }
            await handle_patient_intake(update, context)

        self.assertEqual(context.user_data["patient_flow_state"], PAYMENT_PENDING)
        self.assertIsNone(get_patient_by_identifier("08012345678"))
        update.message.reply_text.assert_awaited_once()

    async def test_plain_private_greeting_opens_home_menu(self):
        update = make_update(101, text="hi")
        context = make_context()

        await route_priority_text_inputs(update, context)

        update.message.reply_text.assert_awaited_once()

    async def test_customer_care_request_is_forwarded_to_admins(self):
        update = make_update(101)
        context = make_context()

        await customer_care_handler(update, context)
        update.message.reply_text.assert_awaited_once()

    async def test_customer_care_can_connect_user_to_human_support(self):
        from synmed_utils.support_registry import (
            available_support_agents,
            get_support_partner,
            support_profiles,
        )

        available_support_agents.add(9001)
        support_profiles[9001] = {"name": "SynMed Support"}
        context = make_context()
        callback_update = SimpleNamespace(
            callback_query=SimpleNamespace(
                data="customerhuman:connect",
                answer=AsyncMock(),
                edit_message_text=AsyncMock(),
                from_user=SimpleNamespace(id=101),
            )
        )

        await customer_care_callback(callback_update, context)

        self.assertEqual(get_support_partner(101), 9001)
        self.assertEqual(context.bot.send_message.await_count, 1)
        callback_update.callback_query.edit_message_text.assert_awaited_once()

    async def test_returning_patient_moves_to_email_collection_before_payment(self):
        patient = register_patient(
            telegram_id=101,
            name="Ada",
            age="29",
            gender="Female",
            phone="08012345678",
            address="Ikeja",
            allergy="Peanuts",
            email="ada@example.com",
        )
        update = make_update(101, text=patient["hospital_number"])
        context = make_context({"patient_flow_state":  "lookup"})

        await handle_patient_intake(update, context)

        self.assertEqual(context.user_data["patient_flow_state"], RETURN_EMAIL)
        self.assertEqual(context.user_data["patient_record"]["hospital_number"], patient["hospital_number"])
        update.message.reply_text.assert_awaited_once()

    async def test_payment_verification_registers_new_patient_and_unlocks_symptom_prompt(self):
        context = make_context(
            {
                "reg_name": "Ada",
                "reg_age": "29",
                "reg_gender": "Female",
                "reg_phone": "08012345678",
                "reg_address": "Ikeja",
                "reg_allergy": "Peanuts",
                "reg_email": "ada@example.com",
                "patient_flow_state": PAYMENT_PENDING,
                "payment_context": {
                    "reference": "synmed-ref-1",
                    "authorization_url": "https://paystack.test/pay/123",
                    "amount": 3000,
                    "currency": "NGN",
                    "patient_type": "new",
                    "label": "SynMed Registration + Consultation Fee",
                    "email": "ada@example.com",
                },
            }
        )
        callback_update = SimpleNamespace(
            callback_query=SimpleNamespace(
                data="payment:verify",
                answer=AsyncMock(),
                edit_message_text=AsyncMock(),
                from_user=SimpleNamespace(id=101),
                message=SimpleNamespace(chat_id=101),
            )
        )

        with patch("handlers.patient.verify_transaction", new=AsyncMock()) as mocked_verify:
            mocked_verify.return_value = {
                "status": "success",
                "amount": 300000,
                "currency": "NGN",
            }
            await handle_payment_callback(callback_update, context)

        self.assertEqual(context.user_data["patient_flow_state"], SYMPTOMS)
        self.assertEqual(context.user_data["patient_record"]["hospital_number"], "SM0001")
        self.assertEqual(
            get_patient_by_identifier("08012345678")["hospital_number"],
            "SM0001",
        )
        self.assertEqual(context.bot.send_message.await_count, 1)

    async def test_doctor_on_consumes_waiting_patient_and_preserves_details(self):
        patient_id = 101
        doctor_id = 202
        registry.queue_patient(
            patient_id,
            {
                "hospital_number": "SM0001",
                "name": "Ada",
                "age": "29",
                "gender": "Female",
                "phone": "08012345678",
                "address": "Ikeja",
                "allergy": "Peanuts",
                "history": "Headache and fever",
                "telegram_id": patient_id,
            },
        )
        doctor_profiles[doctor_id] = {
            "name": "Mensah",
            "specialty": "General Medicine",
            "experience": "7",
            "verified": True,
        }
        update = make_update(doctor_id)
        context = make_context()

        with (
            patch("handlers.doctor.is_verified", return_value=True),
            patch("handlers.doctor.get_average_rating", return_value=4.5),
            patch("handlers.doctor.get_total_ratings", return_value=2),
        ):
            await doctor_on(update, context)

        self.assertEqual(active_chats[patient_id], doctor_id)
        self.assertEqual(active_chats[doctor_id], patient_id)
        self.assertIn(doctor_id, registry.busy_doctors)
        self.assertNotIn(doctor_id, registry.available_doctors)
        self.assertEqual(context.bot.send_message.await_count, 2)

        patient_notice = context.bot.send_message.await_args_list[0].kwargs["text"]
        doctor_notice = context.bot.send_message.await_args_list[1].kwargs["text"]
        self.assertIn("Dr. Mensah", patient_notice)
        self.assertIn("Hospital Number: SM0001", doctor_notice)
        self.assertIn("Ada", doctor_notice)
        self.assertIn("Ikeja", doctor_notice)
        self.assertIn("Peanuts", doctor_notice)
        self.assertIn("Headache and fever", doctor_notice)
        self.assertNotIn("parse_mode", context.bot.send_message.await_args_list[0].kwargs)
        self.assertNotIn("parse_mode", context.bot.send_message.await_args_list[1].kwargs)

    async def test_end_chat_sends_rating_prompt_and_returns_doctor_online_when_queue_empty(self):
        patient_id = 101
        doctor_id = 202
        start_chat(patient_id, doctor_id)
        registry.set_doctor_busy(doctor_id)

        update = make_update(doctor_id)
        context = make_context()

        await end_chat_handler(update, context)
        update.message.reply_text.assert_awaited_once()

        callback_update = SimpleNamespace(
            callback_query=SimpleNamespace(
                data="endchat:confirm",
                answer=AsyncMock(),
                edit_message_text=AsyncMock(),
                from_user=SimpleNamespace(id=doctor_id),
            )
        )

        await end_chat_confirm_handler(callback_update, context)

        self.assertFalse(active_chats)
        self.assertIn(doctor_id, registry.available_doctors)
        self.assertNotIn(doctor_id, registry.busy_doctors)

        messages = [call.kwargs["text"] for call in context.bot.send_message.await_args_list]
        self.assertIn("The consultation has ended.", messages)
        self.assertIn("Consultation ended.", messages)
        self.assertIn("Please rate your consultation:", messages)
        self.assertIn("You are now ONLINE and waiting for patients.", messages)

    async def test_end_chat_reassigns_doctor_to_next_waiting_patient(self):
        current_patient_id = 101
        next_patient_id = 303
        doctor_id = 202
        start_chat(current_patient_id, doctor_id)
        registry.set_doctor_busy(doctor_id)
        registry.queue_patient(
            next_patient_id,
            {
                "hospital_number": "SM0002",
                "name": "Tolu",
                "age": "41",
                "gender": "Male",
                "phone": "08055555555",
                "address": "Yaba",
                "allergy": "None recorded",
                "history": "Back pain",
                "telegram_id": next_patient_id,
            },
        )

        update = make_update(doctor_id)
        context = make_context()

        with patch("handlers.end_chat.format_doctor_intro", return_value="Doctor intro"):
            await end_chat_handler(update, context)
            callback_update = SimpleNamespace(
                callback_query=SimpleNamespace(
                    data="endchat:confirm",
                    answer=AsyncMock(),
                    edit_message_text=AsyncMock(),
                    from_user=SimpleNamespace(id=doctor_id),
                )
            )
            await end_chat_confirm_handler(callback_update, context)

        self.assertEqual(active_chats[next_patient_id], doctor_id)
        self.assertEqual(active_chats[doctor_id], next_patient_id)
        self.assertIn(doctor_id, registry.busy_doctors)
        self.assertNotIn(doctor_id, registry.available_doctors)

        patient_notice = context.bot.send_message.await_args_list[-2].kwargs["text"]
        doctor_notice = context.bot.send_message.await_args_list[-1].kwargs["text"]
        self.assertEqual(patient_notice, "Doctor intro")
        self.assertIn("Hospital Number: SM0002", doctor_notice)
        self.assertIn("Tolu", doctor_notice)
        self.assertIn("Back pain", doctor_notice)
        self.assertNotIn("parse_mode", context.bot.send_message.await_args_list[-2].kwargs)
        self.assertNotIn("parse_mode", context.bot.send_message.await_args_list[-1].kwargs)

    async def test_followup_can_be_scheduled_via_guided_prompt(self):
        patient_id = 101
        doctor_id = 202
        start_chat(
            patient_id,
            doctor_id,
            {
                "hospital_number": "SM0001",
                "name": "Ada",
                "age": "29",
                "gender": "Female",
                "phone": "08012345678",
                "address": "Ikeja",
                "allergy": "Peanuts",
                "history": "Headache and fever",
                "telegram_id": patient_id,
            },
        )
        update = make_update(doctor_id)
        context = make_context()

        with patch("handlers.followups.is_verified", return_value=True):
            await followup_handler(update, context)

            self.assertEqual(context.user_data[FOLLOWUP_STATE_KEY], FOLLOWUP_DATE_STATE)
            update.message.reply_text.assert_awaited_once()

            callback_update = SimpleNamespace(
                callback_query=SimpleNamespace(
                    data="followup_date:2026-03-28",
                    answer=AsyncMock(),
                    edit_message_text=AsyncMock(),
                    from_user=SimpleNamespace(id=doctor_id),
                )
            )
            await handle_followup_date_pick(callback_update, context)
            self.assertEqual(context.user_data[FOLLOWUP_STATE_KEY], FOLLOWUP_TIME_STATE)

            time_update = make_update(doctor_id, text="14:30")
            await handle_followup_input(time_update, context)
            self.assertEqual(context.user_data[FOLLOWUP_STATE_KEY], FOLLOWUP_NOTES_STATE)
            self.assertEqual(
                context.user_data[FOLLOWUP_DRAFT_KEY]["scheduled_for"],
                "2026-03-28 14:30",
            )

            notes_update = make_update(doctor_id, text="Review blood pressure")
            await handle_followup_input(notes_update, context)

        self.assertNotIn(FOLLOWUP_STATE_KEY, context.user_data)
        self.assertEqual(len(get_upcoming_follow_ups()), 1)
        self.assertEqual(context.bot.send_message.await_count, 1)
        self.assertIn("scheduled", notes_update.message.reply_text.await_args_list[0].args[0].lower())

    async def test_followup_date_picker_can_navigate_to_next_week(self):
        patient_id = 101
        doctor_id = 202
        start_chat(
            patient_id,
            doctor_id,
            {
                "hospital_number": "SM0001",
                "name": "Ada",
                "age": "29",
                "gender": "Female",
                "phone": "08012345678",
                "address": "Ikeja",
                "allergy": "Peanuts",
                "history": "Headache and fever",
                "telegram_id": patient_id,
            },
        )
        update = make_update(doctor_id)
        context = make_context()

        with patch("handlers.followups.is_verified", return_value=True):
            await followup_handler(update, context)
            callback_update = SimpleNamespace(
                callback_query=SimpleNamespace(
                    data="followup_nav:1",
                    answer=AsyncMock(),
                    edit_message_text=AsyncMock(),
                    from_user=SimpleNamespace(id=doctor_id),
                )
            )
            await handle_followup_navigation(callback_update, context)

        self.assertEqual(context.user_data[FOLLOWUP_STATE_KEY], FOLLOWUP_DATE_STATE)
        self.assertEqual(context.user_data[FOLLOWUP_DRAFT_KEY]["week_offset"], 1)
        callback_update.callback_query.edit_message_text.assert_awaited_once()

    async def test_emergency_symptoms_trigger_warning_and_admin_alert(self):
        patient_id = 101
        patient = register_patient(
            telegram_id=patient_id,
            name="Ada",
            age="29",
            gender="Female",
            phone="08012345678",
            address="Ikeja",
            allergy="Peanuts",
        )
        update = make_update(patient_id, text="I have chest pain and difficulty breathing")
        context = make_context({
            "patient_record": patient,
            "patient_flow_state": SYMPTOMS,
        })

        with patch("handlers.patient.get_admins", return_value={9001}):
            await handle_patient_intake(update, context)

        self.assertIn(patient_id, registry.waiting_patients)
        self.assertTrue(registry.pending_patient_details[patient_id]["emergency_flag"])
        self.assertIn("chest pain", registry.pending_patient_details[patient_id]["emergency_matches"])
        self.assertEqual(update.message.reply_text.await_count, 2)
        self.assertEqual(context.bot.send_message.await_count, 1)

    async def test_emergency_cases_are_prioritized_in_queue(self):
        registry.queue_patient(201, {"name": "Regular", "emergency_flag": False})
        registry.queue_patient(202, {"name": "Urgent", "emergency_flag": True})

        patient_id, details = registry.pop_waiting_patient()

        self.assertEqual(patient_id, 202)
        self.assertTrue(details["emergency_flag"])

    async def test_end_chat_can_be_cancelled_after_warning(self):
        patient_id = 101
        doctor_id = 202
        start_chat(patient_id, doctor_id)
        registry.set_doctor_busy(doctor_id)

        update = make_update(doctor_id)
        context = make_context()

        await end_chat_handler(update, context)

        callback_update = SimpleNamespace(
            callback_query=SimpleNamespace(
                data="endchat:cancel",
                answer=AsyncMock(),
                edit_message_text=AsyncMock(),
                from_user=SimpleNamespace(id=doctor_id),
            )
        )
        await end_chat_confirm_handler(callback_update, context)

        self.assertTrue(active_chats)
        callback_update.callback_query.edit_message_text.assert_awaited_once_with("End chat cancelled.")

    async def test_due_followup_reminders_can_be_sent_automatically(self):
        patient = register_patient(
            telegram_id=901,
            name="Ada",
            age="29",
            gender="Female",
            phone="08012345000",
            address="Ikeja",
            allergy="Peanuts",
        )
        appointment = schedule_follow_up(
            consultation_id="consult-auto-reminder-1",
            patient_id=patient["hospital_number"],
            doctor_id=202,
            scheduled_for="2026-03-25 10:00",
            notes="Review symptoms",
        )
        bot = SimpleNamespace(send_message=AsyncMock())

        with patch("handlers.admin_ops.get_due_follow_up_reminders") as mocked_due:
            mocked_due.return_value = [
                {
                    "appointment_id": appointment["appointment_id"],
                    "consultation_id": "consult-auto-reminder-1",
                    "patient_id": patient["hospital_number"],
                    "doctor_id": "202",
                    "scheduled_for": "2026-03-25 10:00",
                    "notes": "Review symptoms",
                    "status": "scheduled",
                    "telegram_id": patient["telegram_id"],
                    "name": patient["name"],
                }
            ]
            sent = await send_due_followup_reminders(bot)

        self.assertEqual(sent, 1)
        bot.send_message.assert_awaited_once()
        self.assertEqual(get_upcoming_follow_ups()[0]["status"], "reminded")
