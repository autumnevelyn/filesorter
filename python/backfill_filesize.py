#!/usr/bin/env python3

import sqlite3
from pathlib import Path

# =========================================================
# CONFIG
# =========================================================

SORTED_ROOT = Path("~/winhome/Documents/sorted_recovered_files/").expanduser().resolve()
print(SORTED_ROOT)

DB_PATH = Path("~/sorting_progress.db").expanduser().resolve()
print(DB_PATH)

COMMIT_INTERVAL = 100

# =========================================================
# DB
# =========================================================

conn = sqlite3.connect(DB_PATH)

# =========================================================
# MAIN
# =========================================================

files = []

for path in SORTED_ROOT.rglob("*"):

    if not path.is_file():
        continue

    if path.name.endswith(".db"):
        continue

    files.append(path)

print(f"Found {len(files)} files")

updated = 0
errors = 0

for idx, file_path in enumerate(files, start=1):

    try:

        filesize = file_path.stat().st_size

        conn.execute(
            """
            UPDATE processed_files
            SET filesize = ?
            WHERE destination_path = ?
            """,
            (
                filesize,
                str(file_path)
            )
        )

        updated += 1

    except Exception as e:

        errors += 1

        print(f"ERROR: {file_path}")
        print(f"  {e}")

    if idx % COMMIT_INTERVAL == 0:
        conn.commit()

    if idx % 100 == 0 or idx == len(files):

        print(
            f"{idx}/{len(files)} | "
            f"updated={updated} "
            f"errors={errors}"
        )

conn.commit()
conn.close()

print("\nDone.")