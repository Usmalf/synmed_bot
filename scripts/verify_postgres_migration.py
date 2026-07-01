from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from migrate_sqlite_to_postgres import TABLES, sqlite_table_exists


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare SynMed SQLite and PostgreSQL migration row counts.")
    parser.add_argument("--sqlite-path", required=True, help="Path to the source SQLite database.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""), help="Target PostgreSQL DATABASE_URL.")
    return parser.parse_args()


def sqlite_counts(sqlite_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    counts = {}
    for table in TABLES:
        if not sqlite_table_exists(cursor, table):
            counts[table] = 0
            continue
        cursor.execute(f"SELECT COUNT(*) AS total FROM {table}")
        counts[table] = int(cursor.fetchone()["total"])
    conn.close()
    return counts


def postgres_counts(database_url: str) -> dict[str, int]:
    import psycopg
    from psycopg.rows import dict_row

    counts = {}
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            for table in TABLES:
                cursor.execute(
                    """
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = current_schema() AND table_name = %s
                    """,
                    (table,),
                )
                if not cursor.fetchone():
                    counts[table] = 0
                    continue
                cursor.execute(f'SELECT COUNT(*) AS total FROM "{table}"')
                counts[table] = int(cursor.fetchone()["total"])
    return counts


def main() -> int:
    args = parse_args()
    sqlite_path = Path(args.sqlite_path)
    if not sqlite_path.exists():
        print(f"SQLite database not found: {sqlite_path}", file=sys.stderr)
        return 2
    if not args.database_url:
        print("PostgreSQL DATABASE_URL is required.", file=sys.stderr)
        return 2

    source_counts = sqlite_counts(sqlite_path)
    target_counts = postgres_counts(args.database_url)
    mismatches = []
    print("Migration verification")
    print(f"Source: {sqlite_path}")
    for table in TABLES:
        source = source_counts.get(table, 0)
        target = target_counts.get(table, 0)
        marker = "OK" if source == target else "MISMATCH"
        if source or target or marker != "OK":
            print(f"  {marker:8} {table}: SQLite={source} PostgreSQL={target}")
        if source != target:
            mismatches.append(table)

    if mismatches:
        print(f"Verification failed. Mismatched table(s): {', '.join(mismatches)}", file=sys.stderr)
        return 1

    print("Verification passed. PostgreSQL row counts match SQLite.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
