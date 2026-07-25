"""Clean the database while preserving admin accounts.

Usage:
    python scripts/clean_db.py

Respects CAMPUS_DATA_DIR environment variable.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path


def default_data_dir() -> Path:
    env_dir = os.environ.get("CAMPUS_DATA_DIR")
    if env_dir:
        return Path(env_dir)
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "CampusSmartFlow"
    return Path.home() / ".local" / "share" / "CampusSmartFlow"


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean database, keep admin users.")
    parser.add_argument("--db", default=None, help="Override database path")
    parser.add_argument("--schema", default=None, help="Override schema path")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    db_path = Path(args.db) if args.db else (default_data_dir().resolve() / "app.db")
    schema_path = Path(args.schema) if args.schema else (project_root / "schema.sql").resolve()

    print(f"Database: {db_path}")
    print(f"Schema:   {schema_path}")

    if not db_path.exists():
        print(f"[ERROR] Database not found: {db_path}")
        sys.exit(1)
    if not schema_path.exists():
        print(f"[ERROR] Schema not found: {schema_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")

    admins = conn.execute(
        "SELECT * FROM users WHERE role = 'admin' AND is_active = 1"
    ).fetchall()
    print(f"  Found {len(admins)} admin(s) to preserve.")

    tables = [
        row["name"] for row in
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]

    for table in tables:
        try:
            conn.execute(f'DROP TABLE IF EXISTS "{table}"')
        except sqlite3.OperationalError as exc:
            print(f"  [WARN] Could not drop {table}: {exc}")
    print(f"  Dropped {len(tables)} table(s).")

    schema_sql = schema_path.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.execute("PRAGMA foreign_keys = ON")
    print("  Schema recreated from schema.sql.")

    if admins:
        cols = (
            "username,password_hash,name,student_no,grade,class_name,"
            "contact,role,is_active,must_change_password,"
            "credit_score,credit_recovered_on,created_at"
        )
        placeholders = ",".join(["?"] * 13)
        for admin in admins:
            conn.execute(
                f"INSERT INTO users({cols}) VALUES({placeholders})",
                (
                    admin["username"], admin["password_hash"], admin["name"],
                    admin["student_no"], admin["grade"], admin["class_name"],
                    admin["contact"], admin["role"], admin["is_active"],
                    admin["must_change_password"], admin["credit_score"],
                    admin["credit_recovered_on"], admin["created_at"],
                ),
            )
        print(f"  Re-inserted {len(admins)} admin(s):")
        for admin in admins:
            print(f"    - {admin['username']} ({admin['name']})")
    else:
        print("  No admin to restore. Run the app once to create a default admin.")

    conn.commit()
    conn.close()
    print("\nDone. Database cleaned, admin users preserved.")


if __name__ == "__main__":
    main()
