#!/usr/bin/env python3

import os
import shutil
import random
from pathlib import Path

# =========================================================
# CONFIG
# =========================================================

ROOT = Path("../mock_recovery").resolve()

RECREATE = True

# =========================================================
# HELPERS
# =========================================================

JPEG_HEADER = bytes([
    0xFF, 0xD8, 0xFF, 0xE0,
    0x00, 0x10, 0x4A, 0x46,
    0x49, 0x46, 0x00
])

PNG_HEADER = bytes([
    0x89, 0x50, 0x4E, 0x47,
    0x0D, 0x0A, 0x1A, 0x0A
])

PDF_HEADER = b"%PDF-1.4\n"

ZIP_HEADER = bytes([
    0x50, 0x4B, 0x03, 0x04
])

MP4_HEADER = bytes([
    0x00, 0x00, 0x00, 0x18,
    0x66, 0x74, 0x79, 0x70,
    0x6D, 0x70, 0x34, 0x32
])

# =========================================================
# FILE WRITER
# =========================================================

def write_file(path: Path, header: bytes, size: int = 1024):

    with open(path, "wb") as f:

        f.write(header)

        remaining = max(0, size - len(header))

        f.write(os.urandom(remaining))

# =========================================================
# CLEAN
# =========================================================

if RECREATE and ROOT.exists():
    shutil.rmtree(ROOT)

ROOT.mkdir(parents=True, exist_ok=True)

# =========================================================
# CREATE RECUP DIRS
# =========================================================

recup_dirs = []

for i in range(1, 6):

    d = ROOT / f"recup_dir.{i}"

    d.mkdir(parents=True, exist_ok=True)

    recup_dirs.append(d)

# =========================================================
# NORMAL FILES
# =========================================================

print("Creating normal files...")

write_file(
    recup_dirs[0] / "photo1.jpg",
    JPEG_HEADER,
    5000
)

write_file(
    recup_dirs[0] / "image.png",
    PNG_HEADER,
    7000
)

write_file(
    recup_dirs[1] / "document.pdf",
    PDF_HEADER,
    9000
)

write_file(
    recup_dirs[1] / "archive.zip",
    ZIP_HEADER,
    12000
)

write_file(
    recup_dirs[2] / "video.mp4",
    MP4_HEADER,
    16000
)

# =========================================================
# DUPLICATE CONTENT TEST
# =========================================================

print("Creating duplicate-content files...")

duplicate_payload = JPEG_HEADER + os.urandom(8192)

with open(recup_dirs[2] / "dup1.jpg", "wb") as f:
    f.write(duplicate_payload)

with open(recup_dirs[3] / "dup2.jpg", "wb") as f:
    f.write(duplicate_payload)

with open(recup_dirs[4] / "dup3.bin", "wb") as f:
    f.write(duplicate_payload)

# =========================================================
# SAME NAME COLLISION TEST
# =========================================================

print("Creating filename collision files...")

write_file(
    recup_dirs[0] / "collision.jpg",
    JPEG_HEADER,
    4000
)

write_file(
    recup_dirs[1] / "collision.jpg",
    JPEG_HEADER,
    6000
)

write_file(
    recup_dirs[2] / "collision.jpg",
    JPEG_HEADER,
    8000
)

# =========================================================
# WRONG EXTENSION TESTS
# =========================================================

print("Creating wrong-extension files...")

write_file(
    recup_dirs[3] / "fakejpg.jpg",
    PDF_HEADER,
    5000
)

write_file(
    recup_dirs[3] / "not_a_zip.zip",
    JPEG_HEADER,
    5000
)

write_file(
    recup_dirs[4] / "movie.mp4",
    PNG_HEADER,
    5000
)

# =========================================================
# EXTENSIONLESS FILES
# =========================================================

print("Creating extensionless files...")

write_file(
    recup_dirs[4] / "mysteryfile",
    ZIP_HEADER,
    7000
)

# =========================================================
# EMPTY FILES
# =========================================================

print("Creating empty files...")

(recup_dirs[0] / "empty1.bin").touch()

(recup_dirs[1] / "empty2.jpg").touch()

# =========================================================
# CORRUPTED / PARTIAL FILES
# =========================================================

print("Creating corrupted files...")

with open(recup_dirs[2] / "corrupt_partial_png.png", "wb") as f:
    f.write(PNG_HEADER[:4])

with open(recup_dirs[3] / "corrupt_partial_pdf.pdf", "wb") as f:
    f.write(b"%PD")

# =========================================================
# RANDOM UNKNOWN FILES
# =========================================================

print("Creating unknown/random files...")

for i in range(5):

    with open(recup_dirs[random.randint(0, 4)] / f"random_{i}.dat", "wb") as f:
        f.write(os.urandom(random.randint(512, 4096)))

# =========================================================
# PERMISSION FAILURE TEST (optional)
# =========================================================

print("Creating unreadable file...")

unreadable = recup_dirs[4] / "unreadable.bin"

write_file(
    unreadable,
    ZIP_HEADER,
    4096
)

try:
    unreadable.chmod(0)
except Exception:
    print("Could not remove permissions (non-POSIX filesystem?)")

# =========================================================
# DONE
# =========================================================

print("\nDone.")
print(f"Mock recovery tree created at:\n{ROOT}")
