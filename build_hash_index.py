#!/usr/bin/env python3

import hashlib
import sqlite3
import sys

from datetime import datetime
from pathlib import Path

# =========================================================
# CONFIG
# =========================================================

SORTED_ROOT = Path("/path/to/sorted_output").resolve()

DB_PATH = SORTED_ROOT / "sorting_progress.db"

COMMIT_INTERVAL = 100

HASH_CHUNK_SIZE = 1024 * 1024  # 1 MB

# =========================================================
# DATABASE
# =========================================================

def init_db():

    conn = sqlite3.connect(DB_PATH)

    conn.execute("PRAGMA journal_mode=WAL;")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS file_hashes (
        sha256 TEXT PRIMARY KEY,
        filesize INTEGER,
        detected_type TEXT,
        path TEXT,
        indexed_at TEXT
    )
    """)

    conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_filesize
    ON file_hashes(filesize)
    """)

    conn.commit()

    return conn


# =========================================================
# HASHING
# =========================================================

def sha256_file(file_path: Path) -> str:

    hasher = hashlib.sha256()

    with open(file_path, "rb") as f:

        while True:

            chunk = f.read(HASH_CHUNK_SIZE)

            if not chunk:
                break

            hasher.update(chunk)

    return hasher.hexdigest()


# =========================================================
# HELPERS
# =========================================================

def hash_exists(conn, sha256):

    cur = conn.execute(
        """
        SELECT 1
        FROM file_hashes
        WHERE sha256 = ?
        LIMIT 1
        """,
        (sha256,)
    )

    return cur.fetchone() is not None


def insert_hash(
    conn,
    sha256,
    filesize,
    detected_type,
    path
):

    conn.execute(
        """
        INSERT OR IGNORE INTO file_hashes (
            sha256,
            filesize,
            detected_type,
            path,
            indexed_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            sha256,
            filesize,
            detected_type,
            path,
            datetime.now().isoformat()
        )
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print("Opening database...")

    conn = init_db()

    files = []

    print("Scanning files...")

    for path in SORTED_ROOT.rglob("*"):

        if not path.is_file():
            continue

        if path.name == "sorting_progress.db":
            continue

        if path.suffix == ".db":
            continue

        files.append(path)

    print(f"Found {len(files)} files")

    processed = 0
    skipped = 0
    errors = 0

    for idx, file_path in enumerate(files, start=1):

        try:

            filesize = file_path.stat().st_size

            detected_type = "unknown"

            if len(file_path.parts) >= 2:
                detected_type = file_path.parts[-3]

            sha256 = sha256_file(file_path)

            if hash_exists(conn, sha256):
                skipped += 1
            else:

                insert_hash(
                    conn,
                    sha256,
                    filesize,
                    detected_type,
                    str(file_path)
                )

                processed += 1

        except Exception as e:

            errors += 1

            print(f"ERROR: {file_path}")
            print(f"  {e}")

        if idx % COMMIT_INTERVAL == 0:
            conn.commit()

        if idx % 100 == 0 or idx == len(files):

            print(
                f"{idx}/{len(files)} | "
                f"indexed={processed} "
                f"skipped={skipped} "
                f"errors={errors}"
            )

    conn.commit()
    conn.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
