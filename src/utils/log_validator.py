"""Validation utilities for logs/experiment_data.json.

Teacher-facing goal:
- Prove that every logged interaction includes `input_prompt` and `output_response`.
- Detect corrupted JSON or missing required fields early.

This validator supports your current log format: a JSON list of entries.
"""

from __future__ import annotations

import json
import os
from typing import Any, Iterable, Tuple


LOG_FILE = os.path.join("logs", "experiment_data.json")


REQUIRED_TOP_LEVEL_FIELDS = [
    "id",
    "timestamp",
    "agent",
    "model",
    "action",
    "details",
    "status",
]

REQUIRED_DETAILS_FIELDS = [
    "input_prompt",
    "output_response",
]


def _normalize_entries(data: Any) -> list[dict[str, Any]]:
    """Return a list of log entries, or raise ValueError."""
    if isinstance(data, list):
        if not all(isinstance(x, dict) for x in data):
            raise ValueError("Log file must be a list of objects")
        return data

    # Be tolerant if a different format is produced (some teams use {"experiments": [...]})
    if isinstance(data, dict) and "experiments" in data:
        experiments = data["experiments"]
        if not isinstance(experiments, list) or not all(isinstance(x, dict) for x in experiments):
            raise ValueError("Log file 'experiments' must be a list of objects")
        return experiments

    raise ValueError("Unsupported log JSON format")


def validate_log_entries(entries: Iterable[dict[str, Any]]) -> Tuple[bool, str | None]:
    for idx, entry in enumerate(entries):
        for key in REQUIRED_TOP_LEVEL_FIELDS:
            if key not in entry:
                return False, f"Entry #{idx} missing top-level field: {key}"

        details = entry.get("details")
        if not isinstance(details, dict):
            return False, f"Entry #{idx} has non-dict 'details'"

        for key in REQUIRED_DETAILS_FIELDS:
            if key not in details:
                return False, f"Entry #{idx} missing details field: {key}"

    return True, None


def validate_log_file(path: str = LOG_FILE) -> Tuple[bool, str | None]:
    if not os.path.exists(path):
        return False, f"Log file not found: {path}"

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            return False, "Log file is empty"
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return False, f"Log file is not valid JSON: {e}"
    except OSError as e:
        return False, f"Could not read log file: {e}"

    try:
        entries = _normalize_entries(data)
    except ValueError as e:
        return False, str(e)

    if len(entries) == 0:
        return False, "No experiments logged"

    return validate_log_entries(entries)
