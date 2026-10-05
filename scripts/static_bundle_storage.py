"""Store large frozen ZIPs as Git-sized parts; reconstruct exact release bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

PART_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE = 512 * 1024 * 1024
SCHEMA = "fireatlas-static-archive-storage-v1"


def checksum(path):
    with Path(path).open("rb") as stream:
        digest = hashlib.sha256()
        while block := stream.read(1024 * 1024):
            digest.update(block)
        return digest.hexdigest()


def prepare(data, part_bytes=PART_BYTES, minimum_bytes=95 * 1024 * 1024):
    data = Path(data)
    if not 1 <= part_bytes <= PART_BYTES:
        raise ValueError("Invalid archive part size.")
    release = json.loads((data / "manifest.json").read_text())
    storage = {"schema": SCHEMA, "archives": []}
    for item in release["bundles"].values():
        path = local_path(data, item["path"])
        if not path.is_file() or path.stat().st_size != item["bytes"] or checksum(path) != item["sha256"]:
            raise ValueError("Frozen archive does not match its release manifest.")
        if path.stat().st_size < minimum_bytes:
            continue
        if path.stat().st_size > MAX_ARCHIVE:
            raise ValueError("Archive exceeds the storage limit.")
        entry = {"path": item["path"], "bytes": item["bytes"], "sha256": item["sha256"], "parts": []}
        with path.open("rb") as stream:
            index = 0
            while block := stream.read(part_bytes):
                part = path.with_name(path.name + f".part{index:03d}")
                part.write_bytes(block)
                entry["parts"].append({"path": str(part.relative_to(data)), "bytes": len(block),
                                       "sha256": hashlib.sha256(block).hexdigest()})
                index += 1
        storage["archives"].append(entry)
    # Transport metadata is separate from the unchanged scientific release.
    (data / "bundles" / "archive-storage.json").write_text(json.dumps(storage, indent=2) + "\n")
    return storage


def local_path(data, relative):
    if not isinstance(relative, str) or "\\" in relative:
        raise ValueError("Invalid storage path.")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "bundles":
        raise ValueError("Storage path escapes the archive directory.")
    target = data / path
    if target.is_symlink() or not target.resolve().is_relative_to((data / "bundles").resolve()):
        raise ValueError("External storage paths are forbidden.")
    return target


def assemble(data):
    data = Path(data)
    index = data / "bundles" / "archive-storage.json"
    if not index.exists():
        return []
    storage = json.loads(index.read_text())
    release = json.loads((data / "manifest.json").read_text())
    if storage.get("schema") != SCHEMA:
        raise ValueError("Unsupported archive storage schema.")
    originals = {item["path"]: item for item in release["bundles"].values()}
    done = []
    seen = set()
    for entry in storage["archives"]:
        name = entry["path"]
        original = originals.get(name)
        if name in seen or not original or entry["sha256"] != original["sha256"] or entry["bytes"] != original["bytes"]:
            raise ValueError("Storage identity does not match the scientific release.")
        seen.add(name)
        if not 0 < entry["bytes"] <= MAX_ARCHIVE or not 1 <= len(entry["parts"]) <= 512:
            raise ValueError("Archive exceeds storage limits.")
        target = local_path(data, name)
        if target.is_file() and target.stat().st_size == entry["bytes"] and checksum(target) == entry["sha256"]:
            done.append(name)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".assemble-", delete=False) as output:
                temporary = Path(output.name)
                total = 0
                whole = hashlib.sha256()
                used = set()
                for part in entry["parts"]:
                    if part["path"] in used or not 0 < part["bytes"] <= PART_BYTES:
                        raise ValueError("Invalid or duplicate archive part.")
                    used.add(part["path"])
                    source = local_path(data, part["path"])
                    if source.stat().st_size != part["bytes"]:
                        raise ValueError("Archive part size mismatch.")
                    count = 0
                    digest = hashlib.sha256()
                    with source.open("rb") as stream:
                        while block := stream.read(1024 * 1024):
                            total += len(block)
                            count += len(block)
                            if total > entry["bytes"] or count > part["bytes"]:
                                raise ValueError("Archive part exceeds declared size.")
                            whole.update(block)
                            digest.update(block)
                            output.write(block)
                    if count != part["bytes"] or digest.hexdigest() != part["sha256"]:
                        raise ValueError("Archive part checksum mismatch.")
                if total != entry["bytes"] or whole.hexdigest() != entry["sha256"]:
                    raise ValueError("Reassembled archive checksum mismatch.")
            os.replace(temporary, target)
            temporary = None
            done.append(name)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return done


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=Path("site"))
    parser.add_argument("--prepare", action="store_true", help="Prepare transport parts from verified full ZIPs")
    args = parser.parse_args()
    data = args.site / "data" / "analysis"
    if args.prepare:
        result = prepare(data)
        print(f"Prepared {len(result['archives'])} archives in Git-sized parts.")
    else:
        print(f"Verified/assembled {len(assemble(data))} exact frozen archives.")


if __name__ == "__main__":
    main()
