"""ISIMIP client: parsing, checksums and provenance, without network calls."""

import hashlib
import json

from aadesk.iiasa import DatasetFile, _as_dataset, sha512_of, specifier_match


def _payload():
    return {
        "id": "abc",
        "name": "population_histsoc_national_annual",
        "version": "20210526",
        "size": 498640,
        "specifiers": {"resolution": "national", "time_step": "annual"},
        "rights": {"rights": "CC0 1.0 Universal", "short": "CC0 1.0"},
        "files": [{"id": "f1", "name": "pop.csv", "size": 338985,
                   "checksum": "a" * 128,
                   "path": "ISIMIP2a/InputData/pop.csv", "file_url": ""}],
    }


def test_dataset_parsing_captures_licence():
    dataset = _as_dataset(_payload())
    assert dataset.name == "population_histsoc_national_annual"
    assert dataset.licence_short == "CC0 1.0"
    assert dataset.files[0].name == "pop.csv"


def test_sha512_property_only_accepts_128_hex_digits():
    assert DatasetFile("1", "f", 1, "a" * 128, "p", "").sha512 == "a" * 128
    assert DatasetFile("1", "f", 1, "a" * 32, "p", "").sha512 is None
    assert DatasetFile("1", "f", 1, None, "p", "").sha512 is None


def test_download_url_falls_back_to_file_server():
    file = DatasetFile("1", "f", 1, "a" * 128, "ISIMIP2a/x.csv", "")
    assert file.download_url == "https://files.isimip.org/ISIMIP2a/x.csv"


def test_specifier_match():
    assert specifier_match({"resolution": "national"}, {"resolution": "national"})
    assert not specifier_match({"resolution": "national"}, {"resolution": "global"})


def test_sha512_of_matches_hashlib(tmp_path):
    target = tmp_path / "sample.bin"
    target.write_bytes(b"humanitarian data desk")
    assert sha512_of(target) == hashlib.sha512(b"humanitarian data desk").hexdigest()


def test_provenance_record_is_written(tmp_path):
    from aadesk.iiasa import ISIMIPClient
    client = ISIMIPClient(cache_dir=tmp_path)
    dataset = _as_dataset(_payload())
    target = tmp_path / "pop.csv"
    target.write_text("ISO,Country\n", encoding="utf-8")
    record = client.write_provenance(dataset, target)
    payload = json.loads(record.read_text())
    assert payload["dataset"] == "population_histsoc_national_annual"
    assert payload["licence_short"] == "CC0 1.0"
    assert payload["sha512"]
