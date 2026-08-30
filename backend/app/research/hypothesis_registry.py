"""
Append-only hypothesis registry, backed by a single JSON file.

Every register_hypothesis()/version_hypothesis() call APPENDS a new
record — never overwrites or deletes one. A hypothesis's history is
therefore always fully recoverable: get_hypothesis(id, version=N)
returns exactly what existed at version N, forever.
"""

import json
from dataclasses import replace
from pathlib import Path

from app.research.hypothesis import Hypothesis, new_hypothesis_id


def _load_all(registry_path: str) -> list[dict]:
    path = Path(registry_path)
    if not path.exists():
        return []
    return json.loads(path.read_text())


def _append(registry_path: str, record: dict) -> None:
    records = _load_all(registry_path)
    records.append(record)
    Path(registry_path).write_text(json.dumps(records, indent=2))


def register_hypothesis(hypothesis: Hypothesis, registry_path: str) -> Hypothesis:
    """Registers a new hypothesis at version 1. Raises if hypothesis.id already exists."""
    existing = _load_all(registry_path)
    if any(r["id"] == hypothesis.id for r in existing):
        raise ValueError(
            f"Hypothesis id {hypothesis.id!r} already registered — use version_hypothesis() "
            "to create a new version, or generate a fresh id with new_hypothesis_id()."
        )
    if hypothesis.version != 1:
        raise ValueError("A newly registered hypothesis must start at version=1.")
    _append(registry_path, hypothesis.to_dict())
    return hypothesis


def version_hypothesis(hypothesis_id: str, registry_path: str, **changes) -> Hypothesis:
    """
    Creates and appends a NEW version of an existing hypothesis — the
    previous version's record is untouched in the file. `changes` may
    override any field except `id` (identity never changes) and
    `version` (always auto-incremented).
    """
    current = get_hypothesis(hypothesis_id, registry_path)
    if current is None:
        raise ValueError(f"No hypothesis with id {hypothesis_id!r} found.")
    changes.pop("id", None)
    changes.pop("version", None)
    updated = replace(current, version=current.version + 1, **changes)
    _append(registry_path, updated.to_dict())
    return updated


def get_hypothesis(hypothesis_id: str, registry_path: str, version: int | None = None) -> Hypothesis | None:
    records = [r for r in _load_all(registry_path) if r["id"] == hypothesis_id]
    if not records:
        return None
    if version is not None:
        matches = [r for r in records if r["version"] == version]
        return Hypothesis.from_dict(matches[-1]) if matches else None
    latest = max(records, key=lambda r: r["version"])
    return Hypothesis.from_dict(latest)


def list_hypotheses(registry_path: str, latest_only: bool = True) -> list[Hypothesis]:
    records = _load_all(registry_path)
    if not latest_only:
        return [Hypothesis.from_dict(r) for r in records]
    by_id: dict[str, dict] = {}
    for r in records:
        if r["id"] not in by_id or r["version"] > by_id[r["id"]]["version"]:
            by_id[r["id"]] = r
    return [Hypothesis.from_dict(r) for r in by_id.values()]
