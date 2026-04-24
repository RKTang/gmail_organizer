from __future__ import annotations

from pathlib import Path

from gmail_organizer.config import load_json
from gmail_organizer.engine import apply_plan, build_plan
from gmail_organizer.gmail_client import build_service


def main() -> None:
    project_root = Path(__file__).resolve().parent
    rules_path = project_root / "data" / "gmail_rules.json"
    history_path = project_root / "data" / "gmail_history.json"
    credentials_path = project_root / "data" / "gmail_credentials.json"
    token_path = project_root / "data" / "gmail_token.json"

    if not credentials_path.exists():
        raise FileNotFoundError(f"Missing credentials file: {credentials_path}")
    if not token_path.exists():
        raise FileNotFoundError(
            f"Missing token file: {token_path}. Run gmail_app.py and connect once first."
        )

    config = load_json(rules_path)
    service = build_service(credentials_path, token_path)
    plan, stats = build_plan(service, config)

    print(f"Processed: {stats.processed}")
    print(f"Skipped: {stats.skipped}")
    print(f"Planned changes: {stats.labeled}")

    if not plan:
        print("No changes needed.")
        return

    changed = apply_plan(service, plan, history_path)
    print(f"Applied changes: {changed}")


if __name__ == "__main__":
    main()

