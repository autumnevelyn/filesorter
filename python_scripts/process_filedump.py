#!/usr/bin/env python3

import mimetypes
import shutil
import sqlite3
import sys

from datetime import datetime
from pathlib import Path

# =========================================================
# CONFIG
# =========================================================

SOURCE_ROOT = Path("./mock_recovery_dump/").resolve()
DEST_ROOT = Path("./sorted/").resolve()

DB_PATH = DEST_ROOT / "sorting_progress.db"

MOVE_FILES = True

COMMIT_INTERVAL = 100

# =========================================================
# MAGIC SIGNATURES
# =========================================================

MAGIC_SIGNATURES = [
    (b"\xFF\xD8\xFF", "jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"%PDF", "pdf"),
    (b"PK\x03\x04", "zip"),
    (b"Rar!\x1A\x07\x00", "rar"),
    (b"\x1F\x8B", "gz"),
    (b"ID3", "mp3"),
    (b"OggS", "ogg"),
    (b"fLaC", "flac"),
]


# =========================================================
# DATABASE
# =========================================================

def init_db():
    DEST_ROOT.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS processed_files (
        source_path TEXT PRIMARY KEY,
        recup_dir TEXT,
        detected_type TEXT,
        destination_path TEXT,
        status TEXT,
        processed_at TEXT
    )
    """)

    conn.commit()

    return conn


def already_processed(conn, source_path):
    cur = conn.execute(
        """
        SELECT 1
        FROM processed_files
        WHERE source_path = ?
        LIMIT 1
        """,
        (source_path,)
    )

    return cur.fetchone() is not None


def mark_processed(
    conn,
    source_path,
    recup_dir,
    detected_type,
    destination_path,
    status
):
    conn.execute(
        """
        INSERT OR REPLACE INTO processed_files (
            source_path,
            recup_dir,
            detected_type,
            destination_path,
            status,
            processed_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            source_path,
            recup_dir,
            detected_type,
            destination_path,
            status,
            datetime.now().isoformat()
        )
    )


# =========================================================
# FILE TYPE DETECTION
# =========================================================

def detect_filetype(file_path: Path) -> str:

    try:
        with open(file_path, "rb") as f:
            header = f.read(64)

        # MP4 detection
        # ftyp often appears at offset 4
        if len(header) >= 12 and b"ftyp" in header[4:12]:
            return "mp4"

        for signature, filetype in MAGIC_SIGNATURES:
            if header.startswith(signature):
                return filetype

        mime_type, _ = mimetypes.guess_type(file_path.name)

        if mime_type:
            subtype = mime_type.split("/")[-1]

            # sanitize weird mime names
            subtype = subtype.replace("x-", "")

            return subtype

        return "unknown"

    except Exception:
        return "unknown"


# =========================================================
# FILE MOVING
# =========================================================

def build_destination_path(
    destination_dir: Path,
    original_name: str
) -> Path:

    destination_path = destination_dir / original_name

    if not destination_path.exists():
        return destination_path

    stem = Path(original_name).stem
    suffix = Path(original_name).suffix

    counter = 1

    while True:

        candidate = (
            destination_dir /
            f"{stem}_{counter}{suffix}"
        )

        if not candidate.exists():
            return candidate

        counter += 1


def process_file(conn, file_path: Path, recup_dir_name: str):

    try:
        source_str = str(file_path.resolve())
    except Exception:
        return "error"

    if already_processed(conn, source_str):
        return "skipped"

    filetype = detect_filetype(file_path)

    destination_dir = DEST_ROOT / filetype / recup_dir_name

    try:
        destination_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return "error"

    destination_path = build_destination_path(
        destination_dir,
        file_path.name
    )

    try:

        if MOVE_FILES:
            shutil.move(str(file_path), str(destination_path))
        else:
            shutil.copy2(str(file_path), str(destination_path))

        mark_processed(
            conn,
            source_str,
            recup_dir_name,
            filetype,
            str(destination_path),
            "success"
        )

        return "processed"

    except Exception as e:

        mark_processed(
            conn,
            source_str,
            recup_dir_name,
            filetype,
            str(destination_path),
            f"error: {str(e)}"
        )

        return "error"


# =========================================================
# DIRECTORY PROCESSING
# =========================================================

def process_recup_dir(
    conn,
    recup_dir: Path,
    index: int,
    total: int
):

    print(f"\n[{index}/{total}] {recup_dir.name}")

    processed = 0
    skipped = 0
    errors = 0

    try:
        files = list(recup_dir.iterdir())
    except Exception as e:
        print(f"  Failed to read directory: {e}")
        return

    files = [f for f in files if f.is_file()]

    total_files = len(files)

    for idx, file_path in enumerate(files, start=1):

        result = process_file(
            conn,
            file_path,
            recup_dir.name
        )

        if result == "processed":
            processed += 1
        elif result == "skipped":
            skipped += 1
        else:
            errors += 1

        if idx % 100 == 0 or idx == total_files:
            print(
                f"  {idx}/{total_files} | "
                f"processed={processed} "
                f"skipped={skipped} "
                f"errors={errors}"
            )

        if idx % COMMIT_INTERVAL == 0:
            conn.commit()

    conn.commit()

    print("  Done")


# =========================================================
# MAIN
# =========================================================

def main():

    print("Initializing database...")
    conn = init_db()

    try:

        recup_dirs = sorted(
            [
                d for d in SOURCE_ROOT.iterdir()
                if (
                    d.is_dir()
                    and d.name.startswith("recup_dir.")
                    and d.resolve() != DEST_ROOT
                )
            ],
            key=lambda p: p.name
        )

    except Exception as e:
        print(f"Failed to scan source root: {e}")
        sys.exit(1)

    print(f"Found {len(recup_dirs)} recup directories")

    for index, recup_dir in enumerate(recup_dirs, start=1):

        process_recup_dir(
            conn,
            recup_dir,
            index,
            len(recup_dirs)
        )

    conn.commit()
    conn.close()

    print("\nAll done.")


if __name__ == "__main__":
    main()
