#!/usr/bin/env python3
"""Create or safely unpack the lossless raw experiment evidence archive."""
import argparse
import hashlib
from pathlib import Path
import tarfile

OUT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--unpack", action="store_true")
args = parser.parse_args()
archive = OUT / "raw-evidence.tar.gz"
roots = ("runs", "dumbbell/baseline", "dumbbell/rli")


def digest(file):
    return hashlib.file_digest(file, "sha256").hexdigest()


if args.unpack:
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            target = OUT / member.name
            assert any(member.name == root or member.name.startswith(root + "/") for root in roots)
            assert not member.issym() and not member.islnk()
            if member.isfile() and target.exists():
                with target.open("rb") as existing:
                    assert digest(existing) == digest(tar.extractfile(member)), f"Would overwrite different data: {member.name}"
        tar.extractall(OUT, filter="data")
    print("PASS: raw evidence extracted; any pre-existing files were identical")
else:
    files = [file for root in roots for file in sorted((OUT / root).rglob("*")) if file.is_file()]
    assert files, "No evidence found"
    temporary = OUT / "raw-evidence.tar.gz.tmp"
    with tarfile.open(temporary, "w:gz", compresslevel=6) as tar:
        for file in files:
            tar.add(file, arcname=str(file.relative_to(OUT)), recursive=False)
    with tarfile.open(temporary, "r:gz") as tar:
        members = [member for member in tar.getmembers() if member.isfile()]
        assert len(members) == len(files)
        for member in members:
            with (OUT / member.name).open("rb") as original:
                assert digest(original) == digest(tar.extractfile(member)), member.name
    temporary.replace(archive)
    print(f"PASS: {len(files)} raw evidence files archived and verified byte-for-byte ({archive.stat().st_size / 1024**2:.2f} MiB)")
