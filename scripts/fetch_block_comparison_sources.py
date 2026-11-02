"""Fetch the three pinned Census display reference ZIPs without changing plans.

Use --output-dir with the desired source-cache directory. Existing matching files
are reused; an existing mismatch fails rather than overwriting evidence. Source
ZIPs are never extracted. --verify-only needs no network and changes no files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


SOURCES = (
    {"kind": "tracts", "path": "cb_2020_us_tract_500k.zip", "vintage": 2020,
     "bytes": 62350644, "sha256": "2375fd892078592cb6ede13ec81821923ce575f6d801b00c236bfe1521901394"},
    {"kind": "counties", "path": "cb_2020_us_county_500k.zip", "vintage": 2020,
     "bytes": 12587934, "sha256": "1a45c87a5a0c322514c9d5c9ebcba5eb9df313bd38962f6db56107ba0ccacc6f"},
    {"kind": "congressional", "path": "cb_2025_us_cd119_500k.zip", "vintage": 2025,
     "bytes": 7067743, "sha256": "8e804518d333d67e24e25c61767c6a7c78fd0a0852179e8cc19c36fd66011010"},
)


def source_metadata(spec: dict[str, Any]) -> dict[str, Any]:
    year = spec["vintage"]
    return {**spec,
            "url": f"https://www2.census.gov/geo/tiger/GENZ{year}/shp/{spec['path']}",
            "sourcePage": f"https://www.census.gov/geographies/mapping-files/{year}/geo/carto-boundary-file.html",
            "scale": "1:500,000"}


def verify_file(path: Path, spec: dict[str, Any]) -> None:
    if path.stat().st_size != spec["bytes"]:
        raise ValueError(f"Source size differs from pinned value: {path.name}")
    with path.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    if checksum != spec["sha256"]:
        raise ValueError(f"Source SHA-256 differs from pinned value: {path.name}")
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError(f"Source ZIP CRC validation failed: {path.name}")


def fetch_source(output: Path, spec: dict[str, Any], *, verify_only: bool = False) -> dict[str, Any]:
    filename = str(spec["path"])
    if Path(filename).name != filename or "/" in filename or "\\" in filename:
        raise ValueError("Source path must be a simple filename")
    target = output / filename
    metadata = source_metadata(spec)
    if target.exists():
        verify_file(target, spec)
        return metadata
    if verify_only:
        raise FileNotFoundError(f"Pinned source is absent: {target}")
    output.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{filename}.", suffix=".part", dir=output)
    temporary = Path(temporary_name)
    try:
        request = urllib.request.Request(metadata["url"], headers={"User-Agent": "Mozilla/5.0"})
        with os.fdopen(descriptor, "wb") as destination:
            with urllib.request.urlopen(request, timeout=180) as response:
                downloaded = 0
                while chunk := response.read(1024 * 1024):
                    downloaded += len(chunk)
                    if downloaded > spec["bytes"]:
                        raise ValueError(f"Source exceeds pinned byte count: {filename}")
                    destination.write(chunk)
        verify_file(temporary, spec)
        # An exclusive hard link publishes complete verified bytes without ever
        # overwriting an existing file, including if another downloader raced us.
        try:
            os.link(temporary, target)
        except FileExistsError:
            verify_file(target, spec)
        return metadata
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", "--output", dest="output", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    sources = []
    for spec in SOURCES:
        sources.append(fetch_source(output, spec, verify_only=args.verify_only))
        print(f"Verified {spec['path']} ({spec['bytes']:,} bytes)", flush=True)
    if not args.verify_only:
        manifest = output / "sources.json"
        if manifest.exists():
            existing = json.loads(manifest.read_text(encoding="utf-8"))
            for source in sources:
                matches = [entry for entry in existing.get("sources", []) if entry.get("kind") == source["kind"]]
                if len(matches) != 1 or any(matches[0].get(key) != source[key] for key in ("path", "url", "sha256", "bytes", "vintage")):
                    raise ValueError("Existing source manifest differs from pinned sources; preserved without modification")
        else:
            result = {"schemaVersion": 1, "sources": sources,
                      "purpose": "Display-only reference layers; no district-plan numerical changes",
                      "notes": [
                          "2020 1:500,000 files were replaced May 19, 2023 to align geography layers.",
                          "119th Congress reference serves January 2025 through December 2026.",
                          "Cartographic files generalize coastline boundaries; not for strict shared-edge validation.",
                      ]}
            with manifest.open("x", encoding="utf-8") as stream:
                stream.write(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
