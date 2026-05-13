#!/usr/bin/env python3

import hashlib
import shutil
import sqlite3

from pathlib import Path

# =========================================================
# CONFIG
# =========================================================

NEW_RECOVERY_ROOT = Path("/path/to/new_recovery").resolve()

SORTED_ROOT = Path("/path/to/sorted_output").resolve()

DB_PATH = SORTED_ROOT / "sorting_progress.db"

NEW_FILES_ROOT = Path("./new_unique_files").resolve()

KNOWN_FILES_ROOT = Path("./already_known_files").resolve()

MOVE_FILES = False

COMMIT_INTERVAL = 100

HASH_CHUNK_SIZE = 1024 * 1024  # 1 MB

# =========================================================
# DATABASE
# =========================================================

def open_db():

    conn = sqlite3.connect(DB_PATH)

    conn.execute("PRAGMA journal_mode=WAL;")

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

def hash_exists(conn, sha256, filesize):

    cur = conn.execute(
        """
        SELECT 1
        FROM file_hashes
        WHERE sha256 = ?
        AND filesize = ?
        LIMIT 1
        """,
        (
            sha256,
            filesize
        )
    )

    return cur.fetchone() is not None


def safe_transfer(src: Path, dst: Path):

    dst.parent.mkdir(parents=True, exist_ok=True)

    counter = 1

    original_dst = dst

    while dst.exists():

        stem = original_dst.stem
        suffix = original_dst.suffix

        dst = (
            original_dst.parent /
            f"{stem}_{counter}{suffix}"
        )

        counter += 1

    if MOVE_FILES:
        shutil.move(str(src), str(dst))
    else:
        shutil.copy2(str(src), str(dst))


# =========================================================
# MAIN
# =========================================================

def main():

    conn = open_db()

    files = []

    print("Scanning new recovery dump...")

    for path in NEW_RECOVERY_ROOT.rglob("*"):

        if path.is_file():
            files.append(path)

    print(f"Found {len(files)} files")

    new_count = 0
    known_count = 0
    errors = 0

    for idx, file_path in enumerate(files, start=1):

        try:

            filesize = file_path.stat().st_size

            sha256 = sha256_file(file_path)

            is_known = hash_exists(
                conn,
                sha256,
                filesize
            )

            relative_path = file_path.relative_to(
                NEW_RECOVERY_ROOT
            )

            if is_known:

                destination = (
                    KNOWN_FILES_ROOT /
                    relative_path
                )

                known_count += 1

            else:

                destination = (
                    NEW_FILES_ROOT /
                    relative_path
                )

                new_count += 1

            safe_transfer(
                file_path,
                destination
            )

        except Exception as e:

            errors += 1

            print(f"ERROR: {file_path}")
            print(f"  {e}")

        if idx % 100 == 0 or idx == len(files):

            print(
                f"{idx}/{len(files)} | "
                f"new={new_count} "
                f"known={known_count} "
                f"errors={errors}"
            )

    conn.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
