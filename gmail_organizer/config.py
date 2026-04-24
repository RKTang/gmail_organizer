from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_GMAIL_RULES: dict[str, Any] = {
    "query": "in:inbox -category:primary newer_than:120d",
    "query_presets": [
        "in:inbox newer_than:30d",
        "in:inbox newer_than:60d",
        "in:inbox -category:promotions newer_than:90d",
        "in:inbox -category:social newer_than:90d",
        "in:inbox has:attachment newer_than:120d",
    ],
    "max_results": 200,
    "auto_archive": True,
    "auto_archive_labels": ["Newsletters", "Shopping"],
    "rules": [
        {
            "name": "Newsletters",
            "match": ["newsletter", "unsubscribe", "digest"],
            "label": "Newsletters",
        },
        {
            "name": "Finance",
            "match": ["receipt", "invoice", "payment", "order"],
            "label": "Finance",
        },
        {
            "name": "Work",
            "match": ["github", "alert", "incident", "deploy"],
            "label": "Work",
        },
    ],
    "default_label": "To-Review",
    "ui": {
        "theme": "default",
        "font_size": 10,
        "compact": False,
    },
}


def ensure_json_file(path: Path, default_data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(default_data, indent=2), encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

