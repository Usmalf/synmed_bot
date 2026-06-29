from services.ratings_service import (
    add_review as save_review,
    has_review as review_exists,
)


def has_already_reviewed(consultation_id: str) -> bool:
    return review_exists(consultation_id)


def add_review(
    doctor_id: int,
    patient_id: int,
    rating: int,
    review: str,
    consultation_id: str | None = None,
) -> bool:
    del rating
    if consultation_id is None:
        raise ValueError("consultation_id is required when saving a review")
    return save_review(consultation_id, doctor_id, patient_id, review) is not None
