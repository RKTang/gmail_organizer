from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import load_json, save_json


@dataclass
class MessageChange:
    message_id: str
    added_label_ids: list[str]
    removed_label_ids: list[str]


def append_run(history_path: Path, changes: list[MessageChange]) -> None:
    payload = {"runs": []}
    if history_path.exists():
        payload = load_json(history_path)
        payload.setdefault("runs", [])

    payload["runs"].append(
        {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "changes": [entry.__dict__ for entry in changes],
        }
    )
    save_json(history_path, payload)


def load_last_run(history_path: Path) -> list[MessageChange]:
    if not history_path.exists():
        return []
    payload = load_json(history_path)
    runs = payload.get("runs", [])
    if not runs:
        return []
    last_changes = runs[-1].get("changes", [])
    return [MessageChange(**entry) for entry in last_changes]

