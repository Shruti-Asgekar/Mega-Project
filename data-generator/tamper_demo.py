"""
Tamper Demonstration Utility (Module 10).
Flips a single byte of a verified document on disk to demonstrate tamper-evident detection,
and supports restoring the original file.
"""

import sys
import os
import argparse
from pathlib import Path

def tamper_file(file_path: str) -> None:
    path = Path(file_path)
    if not path.exists():
        print(f"Error: file not found at {file_path}")
        sys.exit(1)

    backup_path = path.with_suffix(path.suffix + ".bak")
    content = bytearray(path.read_bytes())
    if len(content) == 0:
        print("Error: empty file cannot be tampered.")
        sys.exit(1)

    # Save backup if not already present
    if not backup_path.exists():
        backup_path.write_bytes(content)

    # Flip one byte at middle
    idx = len(content) // 2
    content[idx] ^= 0xFF # Invert bits of byte

    path.write_bytes(content)
    print(f"[TAMPER] Flipped byte at offset {idx} in {path.name}.")
    print(f"[TAMPER] Backup preserved at {backup_path.name}.")

def restore_file(file_path: str) -> None:
    path = Path(file_path)
    backup_path = path.with_suffix(path.suffix + ".bak")
    if not backup_path.exists():
        print(f"Error: no backup found at {backup_path}")
        sys.exit(1)

    path.write_bytes(backup_path.read_bytes())
    backup_path.unlink()
    print(f"[RESTORE] Original content restored for {path.name}.")

def main():
    parser = argparse.ArgumentParser(description="Tamper-evident demonstration tool")
    parser.add_argument("file_path", help="Path to document file to tamper/restore")
    parser.add_argument("--restore", action="store_true", help="Restore file to original untampered state")

    args = parser.parse_args()
    if args.restore:
        restore_file(args.file_path)
    else:
        tamper_file(args.file_path)

if __name__ == "__main__":
    main()
