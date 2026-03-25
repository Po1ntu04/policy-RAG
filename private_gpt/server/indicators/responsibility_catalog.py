"""Load responsibility catalogs for indicator extraction."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


_CATALOG_PATH = Path(__file__).with_name("responsibility_catalog.json")


@lru_cache
def load_responsibility_catalog() -> dict:
    if not _CATALOG_PATH.exists():
        return {
            "responsible_units": [],
            "responsible_departments": [],
            "departments_by_unit": {},
        }
    with _CATALOG_PATH.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        return {
            "responsible_units": [],
            "responsible_departments": [],
            "departments_by_unit": {},
        }
    units = data.get("responsible_units") or []
    departments = data.get("responsible_departments") or []
    mapping = data.get("departments_by_unit") or {}
    return {
        "responsible_units": units if isinstance(units, list) else [],
        "responsible_departments": departments if isinstance(departments, list) else [],
        "departments_by_unit": mapping if isinstance(mapping, dict) else {},
    }


def get_responsible_units() -> list[str]:
    return list(load_responsibility_catalog().get("responsible_units") or [])


def get_responsible_departments() -> list[str]:
    return list(load_responsibility_catalog().get("responsible_departments") or [])


def get_departments_by_unit(unit_name: str) -> list[str]:
    if not unit_name:
        return []
    mapping = load_responsibility_catalog().get("departments_by_unit") or {}
    if not isinstance(mapping, dict):
        return []
    return list(mapping.get(unit_name) or [])


def get_departments_for_units(unit_names: list[str]) -> list[str]:
    if not unit_names:
        return []
    mapping = load_responsibility_catalog().get("departments_by_unit") or {}
    if not isinstance(mapping, dict):
        return []
    merged: list[str] = []
    seen = set()
    for name in unit_names:
        for dept in mapping.get(name, []) or []:
            if dept in seen:
                continue
            seen.add(dept)
            merged.append(dept)
    return merged
