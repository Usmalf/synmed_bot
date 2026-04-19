from database import get_connection


def get_admin_analytics():
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) AS total FROM patients")
        patients = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM consultations")
        consultations = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM consultations WHERE status = 'active'")
        active_consultations = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM consultations WHERE status = 'closed'")
        closed_consultations = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM prescriptions")
        prescriptions = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM investigation_requests")
        investigations = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM follow_up_appointments WHERE status = 'scheduled'")
        follow_ups = cursor.fetchone()["total"]

        cursor.execute(
            """
            SELECT doctor_id, COUNT(*) AS total
            FROM consultations
            GROUP BY doctor_id
            ORDER BY total DESC
            LIMIT 1
            """
        )
        busiest_doctor = cursor.fetchone()

    return {
        "patients": patients,
        "consultations": consultations,
        "active_consultations": active_consultations,
        "closed_consultations": closed_consultations,
        "prescriptions": prescriptions,
        "investigations": investigations,
        "follow_ups": follow_ups,
        "busiest_doctor": busiest_doctor["doctor_id"] if busiest_doctor else None,
        "busiest_doctor_count": busiest_doctor["total"] if busiest_doctor else 0,
    }
