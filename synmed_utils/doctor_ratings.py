from services.ratings_service import (
    add_rating as save_rating,
    get_average_rating as fetch_average_rating,
    get_total_ratings as fetch_total_ratings,
    has_rating as rating_exists,
)


def add_rating(
    doctor_id: int,
    rating: int,
    patient_id: int | None = None,
    consultation_id: str | None = None,
):
    if patient_id is None:
        raise ValueError("patient_id is required when saving a rating")
    if consultation_id is None:
        raise ValueError("consultation_id is required when saving a rating")
    return save_rating(consultation_id, doctor_id, patient_id, rating)


def get_average_rating(doctor_id: int) -> float:
    return fetch_average_rating(doctor_id)


def get_total_ratings(doctor_id: int) -> int:
    return fetch_total_ratings(doctor_id)


def has_already_rated(consultation_id: str) -> bool:
    return rating_exists(consultation_id)
