import hashlib
import io
import zipfile

import pytest

from scripts.fetch_block_comparison_sources import fetch_source, source_metadata


def sample_source():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("sample.dbf", b"fixture")
    raw = output.getvalue()
    return raw, {"kind": "tracts", "path": "sample.zip", "vintage": 2020,
                 "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def test_existing_source_is_verified_without_network(tmp_path, monkeypatch):
    raw, spec = sample_source()
    target = tmp_path / spec["path"]
    target.write_bytes(raw)
    monkeypatch.setattr("urllib.request.urlopen", lambda *_a, **_kw: pytest.fail("Network must not be used"))
    assert fetch_source(tmp_path, spec) == source_metadata(spec)
    assert target.read_bytes() == raw


def test_mismatched_existing_source_is_preserved(tmp_path):
    _, spec = sample_source()
    target = tmp_path / spec["path"]
    target.write_bytes(b"old evidence")
    with pytest.raises(ValueError, match="size"):
        fetch_source(tmp_path, spec)
    assert target.read_bytes() == b"old evidence"


def test_verify_only_does_not_create_or_fetch(tmp_path):
    _, spec = sample_source()
    with pytest.raises(FileNotFoundError, match="absent"):
        fetch_source(tmp_path / "absent", spec, verify_only=True)
    assert not (tmp_path / "absent").exists()


def test_verified_download_published_without_part_files(tmp_path, monkeypatch):
    raw, spec = sample_source()
    monkeypatch.setattr("urllib.request.urlopen", lambda *_a, **_kw: io.BytesIO(raw))
    fetch_source(tmp_path, spec)
    assert (tmp_path / spec["path"]).read_bytes() == raw
    assert sorted(p.name for p in tmp_path.iterdir()) == [spec["path"]]


def test_bad_download_is_not_published(tmp_path, monkeypatch):
    raw, spec = sample_source()
    monkeypatch.setattr("urllib.request.urlopen", lambda *_a, **_kw: io.BytesIO(raw[:-1] + b"x"))
    with pytest.raises(ValueError, match="SHA-256"):
        fetch_source(tmp_path, spec)
    assert list(tmp_path.iterdir()) == []


def test_source_path_cannot_escape_output(tmp_path):
    _, spec = sample_source()
    with pytest.raises(ValueError, match="filename"):
        fetch_source(tmp_path, {**spec, "path": "../source.zip"})
