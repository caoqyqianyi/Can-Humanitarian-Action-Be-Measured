"""A thin, checksum-verifying client for the ISIMIP data portal hosted by IIASA.

Why this exists
---------------
Most climate-impact evidence a humanitarian organisation might use sits in
gridded NetCDF on an institutional data portal, behind a catalogue API. The
failure mode is not downloading the file — it is not knowing, three months
later, which version was used, under which licence, and whether the bytes on
disk are the bytes the custodian published. So the client does three things:
resolve a dataset by its specifiers, download with checksum verification, and
write a provenance record next to the data.

API shape verified against https://data.isimip.org/api/v1/ (November 2026).
"""

from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from .config import CACHE_DIR, ensure_dir

BASE_URL = "https://data.isimip.org/api/v1/"
USER_AGENT = "aadesk/0.1 (+https://github.com/; humanitarian data desk)"


class ISIMIPError(RuntimeError):
    """Raised when the portal returns something the client cannot use."""


class ChecksumMismatch(ISIMIPError):
    """Raised when a downloaded file does not match its published digest."""


@dataclass
class DatasetFile:
    id: str
    name: str
    size: int
    checksum: str | None
    path: str
    url: str

    @property
    def sha512(self) -> str | None:
        # The portal publishes a 128-hex-digit digest, i.e. SHA-512.
        if self.checksum and len(self.checksum) == 128:
            return self.checksum.lower()
        return None

    @property
    def download_url(self) -> str:
        if self.url:
            return self.url
        return "https://files.isimip.org/" + self.path


@dataclass
class Dataset:
    id: str
    name: str
    version: str
    size: int
    specifiers: dict
    rights: dict
    files: list[DatasetFile] = field(default_factory=list)
    landing_page: str = ""

    @property
    def licence(self) -> str:
        return (self.rights or {}).get("rights", "unspecified")

    @property
    def licence_short(self) -> str:
        return (self.rights or {}).get("short", "unspecified")


def _as_dataset(payload: dict) -> Dataset:
    files = [
        DatasetFile(
            id=f.get("id", ""),
            name=f.get("name", ""),
            size=int(f.get("size") or 0),
            checksum=f.get("checksum"),
            path=f.get("path", ""),
            url=f.get("file_url") or "",
        )
        for f in (payload.get("files") or [])
    ]
    return Dataset(
        id=payload.get("id", ""),
        name=payload.get("name", ""),
        version=str(payload.get("version", "")),
        size=int(payload.get("size") or 0),
        specifiers=payload.get("specifiers") or {},
        rights=payload.get("rights") or {},
        files=files,
        landing_page=payload.get("metadata_url", ""),
    )


def sha512_of(path: Path | str, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha512()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def specifier_match(specifiers: dict, wanted: dict) -> bool:
    """True when every requested specifier equals the dataset's value."""
    return all(str(specifiers.get(key, "")).lower() == str(value).lower()
               for key, value in wanted.items())


class ISIMIPClient:
    def __init__(self, cache_dir: Path | str = CACHE_DIR, base_url: str = BASE_URL,
                 timeout: int = 45, page_size: int = 100):
        self.cache_dir = ensure_dir(cache_dir)
        self.base_url = base_url
        self.timeout = timeout
        self.page_size = page_size
        self._catalogue: list[Dataset] | None = None

    # ---------------------------------------------------------------- transport
    def _get_json(self, url: str) -> dict:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                      "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except Exception as exc:  # pragma: no cover - network dependent
            raise ISIMIPError(f"request to {url} failed: {exc}") from exc

    # ---------------------------------------------------------------- catalogue
    def catalogue(self, refresh: bool = False) -> list[Dataset]:
        """All publicly listed datasets, cached in memory per client."""
        if self._catalogue is not None and not refresh:
            return self._catalogue
        datasets: list[Dataset] = []
        page = 1
        while True:
            url = f"{self.base_url}datasets/?page_size={self.page_size}&page={page}"
            payload = self._get_json(url)
            datasets.extend(_as_dataset(item) for item in payload.get("results", []))
            if not payload.get("next"):
                break
            page += 1
        self._catalogue = datasets
        return datasets

    def find(self, name: str | None = None, **specifiers) -> list[Dataset]:
        hits = []
        for dataset in self.catalogue():
            if name and dataset.name != name:
                continue
            if specifiers and not specifier_match(dataset.specifiers, specifiers):
                continue
            hits.append(dataset)
        return hits

    def first(self, name: str | None = None, **specifiers) -> Dataset:
        hits = self.find(name=name, **specifiers)
        if not hits:
            raise ISIMIPError(f"no dataset matched name={name!r} specifiers={specifiers}")
        smallest = min(hits, key=lambda d: d.size)
        if len(hits) > 1:
            print(f"  {len(hits)} datasets matched; using the smallest "
                  f"({smallest.size/1e6:.2f} MB): {smallest.name}")
        return smallest

    def dataset(self, dataset_id: str) -> Dataset:
        return _as_dataset(self._get_json(f"{self.base_url}datasets/{dataset_id}/"))

    # ------------------------------------------------------------------- files
    def download(self, dataset: Dataset, file: DatasetFile | None = None,
                 dest_dir: Path | str | None = None, verify: bool = True) -> Path:
        file = file or dataset.files[0]
        dest_dir = ensure_dir(dest_dir or self.cache_dir)
        target = Path(dest_dir) / file.name
        if target.exists() and verify and file.sha512:
            if sha512_of(target) == file.sha512:
                print(f"  cached, checksum ok: {target.name}")
                self.write_provenance(dataset, target)
                return target

        request = urllib.request.Request(file.download_url,
                                         headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=max(self.timeout, 120)) as response:
            payload = response.read()
        target.write_bytes(payload)

        if verify and file.sha512:
            actual = sha512_of(target)
            if actual != file.sha512:
                target.unlink(missing_ok=True)
                raise ChecksumMismatch(
                    f"{file.name}: published {file.sha512[:16]}… != received {actual[:16]}…")
        self.write_provenance(dataset, target)
        return target

    # -------------------------------------------------------------- provenance
    def write_provenance(self, dataset: Dataset, local_path: Path) -> Path:
        record = {
            "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "dataset": dataset.name,
            "dataset_id": dataset.id,
            "version": dataset.version,
            "portal": self.base_url,
            "landing_page": dataset.landing_page,
            "licence": dataset.licence,
            "licence_short": dataset.licence_short,
            "specifiers": dataset.specifiers,
            "local_file": local_path.name,
            "bytes": local_path.stat().st_size if local_path.exists() else None,
            "sha512": sha512_of(local_path) if local_path.exists() else None,
            "note": "Retrieved by aadesk.iiasa; digest re-checked after download.",
        }
        out = local_path.with_suffix(local_path.suffix + ".provenance.json")
        out.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return out


def describe(datasets: Iterable[Dataset]) -> Iterator[str]:
    for dataset in datasets:
        yield (f"{dataset.size/1e6:8.2f} MB  {dataset.name[:70]:70s}  "
               f"{dataset.licence_short}")
