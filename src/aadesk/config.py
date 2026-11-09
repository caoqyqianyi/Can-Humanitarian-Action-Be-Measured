"""Repository paths and small IO helpers."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("AADESK_ROOT", Path(__file__).resolve().parents[2]))

CONFIG_DIR = ROOT / "config"
REGISTRY_FILE = CONFIG_DIR / "registry" / "indicators.yml"
SOURCES_FILE = CONFIG_DIR / "sources.yml"

DATA_DIR = ROOT / "data"
REFERENCE_DIR = DATA_DIR / "reference"
CACHE_DIR = DATA_DIR / "cache"
EXAMPLES_DIR = DATA_DIR / "examples"
OUTPUT_DIR = ROOT / "output"

POPULATION_REFERENCE = REFERENCE_DIR / "isimip_hyde_national_population_1901_2020.csv"


def load_yaml(path: Path | str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def ensure_dir(path: Path | str) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path
