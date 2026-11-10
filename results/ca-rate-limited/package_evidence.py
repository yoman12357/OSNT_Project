#!/usr/bin/env python3
"""Preserve and safely restore raw evidence for the three-phase experiment."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile

OUT = Path(__file__).resolve().parent
ARCHIVE = OUT / "raw-evidence.tar.gz"


def digest(stream):
    return hashlib.file_digest(stream, "sha256").hexdigest()


def valid_name(name):
    path = PurePosixPath(name)
    return (not path.is_absolute() and ".." not in path.parts and len(path.parts) == 4
            and path.parts[1] in ("baseline", "rli")
            and re.fullmatch(r"run-\d+", path.parts[2]) is not None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unpack", action="store_true")
    args = parser.parse_args()
    if args.unpack:
        with tarfile.open(ARCHIVE, "r:gz") as archive:
            for member in archive.getmembers():
                assert member.isfile() and valid_name(member.name), f"Unsafe member: {member.name}"
                target = OUT / member.name
                assert target.resolve().is_relative_to(OUT.resolve())
                if target.exists():
                    with target.open("rb") as existing:
                        assert digest(existing) == digest(archive.extractfile(member)), f"Would overwrite different data: {target}"
            archive.extractall(OUT, filter="data")
        print("PASS: evidence restored; all pre-existing files were identical")
        return
    files = [p for p in sorted(OUT.glob("*/*/run-*/*"))
             if p.is_file() and valid_name(str(p.relative_to(OUT)))
             and (p.name.endswith(".qlog.gz") or p.suffix in (".csv", ".json", ".log"))]
    assert files
    temporary = ARCHIVE.with_name(ARCHIVE.name + ".tmp")
    with tarfile.open(temporary, "w:gz") as archive:
        for path in files:
            archive.add(path, arcname=str(path.relative_to(OUT)), recursive=False)
    hashes = {}
    with tarfile.open(temporary, "r:gz") as archive:
        members = archive.getmembers()
        assert len(members) == len(files)
        for member in members:
            assert member.isfile() and valid_name(member.name)
            hashes[member.name] = digest(archive.extractfile(member))
            with (OUT / member.name).open("rb") as source:
                assert digest(source) == hashes[member.name]
    temporary.replace(ARCHIVE)
    with ARCHIVE.open("rb") as source:
        archive_hash = digest(source)
    check = {"pass": True, "files": len(files),
             "qlogs": sum(p.name.endswith(".qlog.gz") for p in files),
             "archive_sha256": archive_hash, "verified_byte_for_byte": True,
             "scope": "Raw-data integrity, not a verdict on whether the CA cap was exercised.",
             "file_sha256": hashes}
    (OUT / "archive-checks.json").write_text(json.dumps(check, indent=2) + "\n")
    print(f"PASS: {len(files)} raw files archived and verified byte-for-byte")


if __name__ == "__main__":
    main()
