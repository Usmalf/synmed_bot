import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from telegram.ext import ConversationHandler

from database import init_db
from handlers.rate_doctor import handle_review
from services.ratings_service import (
    add_rating,
    add_review,
    get_average_rating,
    get_reviews,
    get_total_ratings,
    has_rating,
    has_review,
)


class TestRatingsService(unittest.TestCase):
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

    def test_add_and_get_rating(self):
        doctor_id = 123
        patient_id = 456
        rating = 4

        result = add_rating("consult-1", doctor_id, patient_id, rating)
        self.assertEqual(result["rating"], rating)
        self.assertTrue(has_rating("consult-1"))

        avg = get_average_rating(doctor_id)
        self.assertEqual(avg, 4.0)
        self.assertEqual(get_total_ratings(doctor_id), 1)

    def test_update_rating_same_consultation(self):
        doctor_id = 123
        patient_id = 456

        add_rating("consult-1", doctor_id, patient_id, 4)
        add_rating("consult-1", doctor_id, patient_id, 5)

        avg = get_average_rating(doctor_id)
        self.assertEqual(avg, 5.0)
        self.assertEqual(get_total_ratings(doctor_id), 1)

    def test_same_patient_can_rate_same_doctor_in_new_consultation(self):
        doctor_id = 123
        patient_id = 456

        add_rating("consult-1", doctor_id, patient_id, 4)
        add_rating("consult-2", doctor_id, patient_id, 5)

        avg = get_average_rating(doctor_id)
        self.assertEqual(avg, 4.5)
        self.assertEqual(get_total_ratings(doctor_id), 2)

    def test_add_and_get_review(self):
        doctor_id = 123
        patient_id = 789
        review_text = "Great doctor, very attentive."

        result = add_review("consult-review-1", doctor_id, patient_id, review_text)
        self.assertEqual(result["review"], review_text)
        self.assertTrue(has_review("consult-review-1"))

        reviews = get_reviews(doctor_id)
        self.assertTrue(any(r["review"] == review_text for r in reviews))

    def test_duplicate_review_returns_none(self):
        doctor_id = 123
        patient_id = 789

        add_review("consult-review-1", doctor_id, patient_id, "Helpful consultation")
        duplicate = add_review("consult-review-1", doctor_id, patient_id, "Second review")

        self.assertIsNone(duplicate)
        self.assertEqual(len(get_reviews(doctor_id)), 1)

    def test_same_patient_can_review_same_doctor_in_new_consultation(self):
        doctor_id = 123
        patient_id = 789

        first = add_review("consult-review-1", doctor_id, patient_id, "Helpful consultation")
        second = add_review("consult-review-2", doctor_id, patient_id, "Another great visit")

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(len(get_reviews(doctor_id)), 2)

    def test_handle_review_accepts_no_and_yes(self):
        async def run_checks():
            update_no = SimpleNamespace(
                message=SimpleNamespace(text="no", reply_text=AsyncMock()),
                effective_user=SimpleNamespace(id=789),
            )
            context_no = SimpleNamespace(
                user_data={
                    "pending_review_doctor": 123,
                    "pending_review_rating": 5,
                    "pending_review_consultation": "consult-review-1",
                }
            )

            result_no = await handle_review(update_no, context_no)
            self.assertEqual(result_no, -1)
            update_no.message.reply_text.assert_awaited_once()
            self.assertIn(
                "consultation has been completed",
                update_no.message.reply_text.await_args_list[0].args[0].lower(),
            )
            self.assertFalse(context_no.user_data)

            update_yes = SimpleNamespace(
                message=SimpleNamespace(text="yes", reply_text=AsyncMock()),
                effective_user=SimpleNamespace(id=789),
            )
            context_yes = SimpleNamespace(
                user_data={
                    "pending_review_doctor": 123,
                    "pending_review_rating": 5,
                    "pending_review_consultation": "consult-review-2",
                }
            )

            result_yes = await handle_review(update_yes, context_yes)
            self.assertEqual(result_yes, 5)
            update_yes.message.reply_text.assert_awaited_once()
            self.assertIn("pending_review_consultation", context_yes.user_data)

        import asyncio
        asyncio.run(run_checks())

    def test_handle_review_submits_review_text_and_clears_session(self):
        async def run_checks():
            update = SimpleNamespace(
                message=SimpleNamespace(
                    text="Very attentive and clear.",
                    reply_text=AsyncMock(),
                ),
                effective_user=SimpleNamespace(id=789),
            )
            context = SimpleNamespace(
                user_data={
                    "pending_review_doctor": 123,
                    "pending_review_rating": 5,
                    "pending_review_consultation": "consult-review-3",
                }
            )

            result = await handle_review(update, context)

            self.assertEqual(result, ConversationHandler.END)
            update.message.reply_text.assert_awaited_once()
            self.assertEqual(context.user_data, {})
            reviews = get_reviews(123)
            self.assertTrue(
                any(r["review"] == "Very attentive and clear." for r in reviews)
            )

        import asyncio
        asyncio.run(run_checks())


if __name__ == "__main__":
    unittest.main()
