from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


TABLES = [
    "doctors",
    "patients",
    "payments",
    "dismissed_payment_attention",
    "consultations",
    "consultation_messages",
    "consultation_timeline",
    "admin_audit_logs",
    "follow_up_appointments",
    "prescriptions",
    "investigation_requests",
    "clinical_letters",
    "admin_alert_states",
    "internal_messages",
    "operational_error_logs",
    "medical_report_requests",
    "partner_facilities",
    "partner_requests",
    "admin_accounts",
    "admin_email_reminders",
    "customer_care_accounts",
    "support_tickets",
    "support_ticket_messages",
    "support_ticket_logs",
    "support_ticket_feedback",
    "patient_consents",
    "doctor_ratings",
    "doctor_reviews",
    "doctor_profiles",
    "pending_doctor_requests",
    "doctor_runtime_presence",
    "waiting_patients_runtime",
    "active_consultations_runtime",
    "consultation_calls_runtime",
    "support_runtime_presence",
    "support_waiting_runtime",
    "support_active_chats_runtime",
    "auth_otps",
    "health_tips",
    "app_settings",
]


AUTO_ID_COLUMNS = {
    "admin_audit_logs": "id",
    "auth_otps": "id",
    "clinical_letters": "id",
    "consultation_messages": "id",
    "consultation_timeline": "id",
    "consultations": "id",
    "customer_care_accounts": "account_id",
    "doctor_ratings": "id",
    "doctor_reviews": "id",
    "doctors": "id",
    "follow_up_appointments": "id",
    "health_tips": "id",
    "internal_messages": "id",
    "investigation_requests": "id",
    "medical_report_requests": "id",
    "operational_error_logs": "id",
    "patient_consents": "id",
    "patients": "id",
    "payments": "id",
    "prescriptions": "id",
    "support_ticket_feedback": "id",
    "support_ticket_logs": "id",
    "support_ticket_messages": "id",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import SynMed SQLite data into PostgreSQL.")
    parser.add_argument("--sqlite-path", required=True, help="Path to the source SQLite database.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""), help="Target PostgreSQL DATABASE_URL.")
    parser.add_argument("--replace", action="store_true", help="Clear target tables before importing.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be copied without writing to PostgreSQL.")
    return parser.parse_args()


def sqlite_columns(cursor: sqlite3.Cursor, table: str) -> list[str]:
    cursor.execute(f"PRAGMA table_info({table})")
    return [row["name"] for row in cursor.fetchall()]


def sqlite_table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    )
    return cursor.fetchone() is not None


def postgres_columns(cursor, table: str) -> list[str]:
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    return [row["column_name"] for row in cursor.fetchall()]


def table_counts(sqlite_conn: sqlite3.Connection) -> dict[str, int]:
    cursor = sqlite_conn.cursor()
    counts = {}
    for table in TABLES:
        if not sqlite_table_exists(cursor, table):
            counts[table] = 0
            continue
        cursor.execute(f"SELECT COUNT(*) AS total FROM {table}")
        counts[table] = int(cursor.fetchone()["total"])
    return counts


def target_has_data(pg_cursor) -> bool:
    for table in TABLES:
        pg_cursor.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = current_schema() AND table_name = %s
            """,
            (table,),
        )
        if not pg_cursor.fetchone():
            continue
        pg_cursor.execute(f'SELECT 1 FROM "{table}" LIMIT 1')
        if pg_cursor.fetchone():
            return True
    return False


def clear_target(pg_cursor) -> None:
    table_list = ", ".join(f'"{table}"' for table in TABLES)
    pg_cursor.execute(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE")


def copy_table(sqlite_conn: sqlite3.Connection, pg_cursor, table: str) -> int:
    sqlite_cursor = sqlite_conn.cursor()
    if not sqlite_table_exists(sqlite_cursor, table):
        return 0

    source_columns = sqlite_columns(sqlite_cursor, table)
    target_columns = postgres_columns(pg_cursor, table)
    columns = [column for column in source_columns if column in target_columns]
    if not columns:
        return 0

    sqlite_cursor.execute(f'SELECT {", ".join(columns)} FROM {table}')
    rows = sqlite_cursor.fetchall()
    if not rows:
        return 0

    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    values = [tuple(row[column] for column in columns) for row in rows]
    pg_cursor.executemany(
        f'INSERT INTO "{table}" ({quoted_columns}) VALUES ({placeholders})',
        values,
    )
    return len(values)


def refresh_sequence(pg_cursor, table: str) -> None:
    column = AUTO_ID_COLUMNS.get(table)
    if not column:
        return
    pg_cursor.execute("SELECT pg_get_serial_sequence(%s, %s) AS sequence_name", (table, column))
    row = pg_cursor.fetchone()
    sequence_name = row["sequence_name"] if row else None
    if not sequence_name:
        return
    pg_cursor.execute(f'SELECT MAX("{column}") AS max_id FROM "{table}"')
    max_id = pg_cursor.fetchone()["max_id"]
    if max_id is None:
        pg_cursor.execute("SELECT setval(%s, 1, false)", (sequence_name,))
    else:
        pg_cursor.execute("SELECT setval(%s, %s, true)", (sequence_name, max_id))


def main() -> int:
    args = parse_args()
    sqlite_path = Path(args.sqlite_path)
    if not sqlite_path.exists():
        print(f"SQLite database not found: {sqlite_path}", file=sys.stderr)
        return 2
    if not args.database_url:
        print("PostgreSQL DATABASE_URL is required.", file=sys.stderr)
        return 2

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    counts = table_counts(sqlite_conn)
    total_rows = sum(counts.values())
    print(f"Source: {sqlite_path}")
    print(f"Rows to inspect/import: {total_rows}")
    for table, count in counts.items():
        if count:
            print(f"  {table}: {count}")

    if args.dry_run:
        sqlite_conn.close()
        return 0

    os.environ["DATABASE_URL"] = args.database_url
    os.environ["DATABASE_PATH"] = str(sqlite_path)

    import psycopg
    from psycopg.rows import dict_row
    from database import init_db

    init_db()

    with psycopg.connect(args.database_url, row_factory=dict_row) as pg_conn:
        with pg_conn.cursor() as pg_cursor:
            if target_has_data(pg_cursor):
                if not args.replace:
                    print(
                        "Target PostgreSQL database already has data. "
                        "Re-run with --replace to clear target tables before import.",
                        file=sys.stderr,
                    )
                    sqlite_conn.close()
                    return 3
                clear_target(pg_cursor)

            imported = {}
            for table in TABLES:
                imported[table] = copy_table(sqlite_conn, pg_cursor, table)
            for table in TABLES:
                refresh_sequence(pg_cursor, table)
        pg_conn.commit()

    sqlite_conn.close()
    print("Import complete.")
    for table, count in imported.items():
        if count:
            print(f"  {table}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
