#!/usr/bin/env python3

import os
import random
import shutil
from pathlib import Path

# =========================================================
# CONFIG
# =========================================================

OUTPUT_ROOT = Path("./mock_recovery_dump")

NUM_RECUP_DIRS = 10

FILES_PER_DIR = 50

# If True, wipes existing mock directory first
DELETE_EXISTING = True

# =========================================================
# FILE TEMPLATES
# =========================================================

FILE_TYPES = {

    "jpeg": {
        "signature": b"\xFF\xD8\xFF\xE0",
        "extension": ".jpg",
        "payload_size": 2048
    },

    "png": {
        "signature": b"\x89PNG\r\n\x1a\n",
        "extension": ".png",
        "payload_size": 4096
    },

    "gif": {
        "signature": b"GIF89a",
        "extension": ".gif",
        "payload_size": 1024
    },

    "pdf": {
        "signature": b"%PDF-1.4\n",
        "extension": ".pdf",
        "payload_size": 8192
    },

    "zip": {
        "signature": b"PK\x03\x04",
        "extension": ".zip",
        "payload_size": 4096
    },

    "mp3": {
        "signature": b"ID3",
        "extension": ".mp3",
        "payload_size": 8192
    },

    "mp4": {
        "signature": (
            b"\x00\x00\x00\x18"
            b"ftypmp42"
        ),
        "extension": ".mp4",
        "payload_size": 16384
    },

    "unknown": {
        "signature": os.urandom(16),
        "extension": ".bin",
        "payload_size": 2048
    }
}

# =========================================================
# HELPERS
# =========================================================

def random_bytes(size):
    return os.urandom(size)


def generate_file_content(filetype_info):

    signature = filetype_info["signature"]

    payload_size = filetype_info["payload_size"]

    payload = random_bytes(payload_size)

    return signature + payload


def create_mock_file(directory, filename, filetype_info):

    path = directory / filename

    content = generate_file_content(filetype_info)

    with open(path, "wb") as f:
        f.write(content)


# =========================================================
# MAIN GENERATION
# =========================================================

def main():

    if DELETE_EXISTING and OUTPUT_ROOT.exists():

        print(f"Deleting existing directory: {OUTPUT_ROOT}")

        shutil.rmtree(OUTPUT_ROOT)

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    print(f"Creating mock recovery dump at:")
    print(f"  {OUTPUT_ROOT}")
    print()

    filetype_names = list(FILE_TYPES.keys())

    total_files = 0

    for dir_index in range(1, NUM_RECUP_DIRS + 1):

        recup_dir = OUTPUT_ROOT / f"recup_dir.{dir_index}"

        recup_dir.mkdir(parents=True, exist_ok=True)

        print(f"Creating {recup_dir.name}")

        for file_index in range(1, FILES_PER_DIR + 1):

            chosen_type = random.choice(filetype_names)

            type_info = FILE_TYPES[chosen_type]

            extension = type_info["extension"]

            # Intentionally messy filenames
            filename_styles = [

                f"f{file_index}{extension}",
                f"recovered_{file_index}",
                f"image_{random.randint(1000,9999)}{extension}",
                f"file_{random.randint(10000,99999)}",
                f"data_{file_index}.dat",
            ]

            filename = random.choice(filename_styles)

            create_mock_file(
                recup_dir,
                filename,
                type_info
            )

            total_files += 1

    print()
    print("Done.")
    print(f"Created {NUM_RECUP_DIRS} recup dirs")
    print(f"Created {total_files} files")


if __name__ == "__main__":
    main()
