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

BATCH_SIZE = 5000

# =========================================================
# DB
# =========================================================

conn = sqlite3.connect(DB_PATH)

# =========================================================
# CREATE STAGING TABLE
# =========================================================

print("Creating staging table...")

conn.execute("""
CREATE TABLE IF NOT EXISTS filesize_staging (
    destination_path TEXT PRIMARY KEY,
    filesize INTEGER
)
""")

conn.execute("""
CREATE INDEX IF NOT EXISTS idx_staging_destination
ON filesize_staging(destination_path)
""")

conn.commit()

# =========================================================
# SCAN FILES
# =========================================================

print("Scanning sorted files...")

files = []

for path in SORTED_ROOT.rglob("*"):

    if not path.is_file():
        continue

    if path.name.endswith(".db"):
        continue

    files.append(path)

print(f"Found {len(files)} files")

# =========================================================
# POPULATE STAGING TABLE
# =========================================================

print("Populating staging table...")

conn.execute("BEGIN")

batch = []

inserted = 0
errors = 0

for idx, file_path in enumerate(files, start=1):

    try:

        filesize = file_path.stat().st_size

        batch.append((
            str(file_path),
            filesize
        ))

        if len(batch) >= BATCH_SIZE:

            conn.executemany(
                """
                INSERT OR REPLACE INTO filesize_staging (
                    destination_path,
                    filesize
                )
                VALUES (?, ?)
                """,
                batch
            )

            inserted += len(batch)

            batch.clear()

    except Exception as e:

        errors += 1

        print(f"ERROR: {file_path}")
        print(f"  {e}")

    if idx % 1000 == 0 or idx == len(files):

        print(
            f"{idx}/{len(files)} | "
            f"staged={inserted} "
            f"errors={errors}"
        )

# final partial batch

if batch:

    conn.executemany(
        """
        INSERT OR REPLACE INTO filesize_staging (
            destination_path,
            filesize
        )
        VALUES (?, ?)
        """,
        batch
    )

    inserted += len(batch)

conn.commit()

print(f"Inserted {inserted} staging rows")

# =========================================================
# ENSURE MAIN INDEX EXISTS
# =========================================================

print("Ensuring destination_path index exists...")

conn.execute("""
CREATE INDEX IF NOT EXISTS idx_destination_path
ON processed_files(destination_path)
""")

conn.commit()

# =========================================================
# BULK UPDATE
# =========================================================

print("Updating processed_files...")

conn.execute("BEGIN")

conn.execute("""
UPDATE processed_files
SET filesize = (
    SELECT filesize_staging.filesize
    FROM filesize_staging
    WHERE filesize_staging.destination_path =
          processed_files.destination_path
)
WHERE filesize IS NULL
AND EXISTS (
    SELECT 1
    FROM filesize_staging
    WHERE filesize_staging.destination_path =
          processed_files.destination_path
)
""")

conn.commit()

# =========================================================
# CLEANUP
# =========================================================

print("Dropping staging table...")

conn.execute("""
DROP TABLE filesize_staging
""")

conn.commit()

conn.close()

print("\nDone.")
