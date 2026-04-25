from pathlib import Path

from gmail_organizer.config import DEFAULT_GMAIL_RULES, ensure_json_file
from gmail_organizer.ui import GmailOrganizerApp


def main() -> None:
    project_root = Path(__file__).resolve().parent
    rules_path = project_root / "data" / "gmail_rules.json"
    history_path = project_root / "data" / "gmail_history.json"
    credentials_path = project_root / "data" / "gmail_credentials.json"
    token_path = project_root / "data" / "gmail_token.json"

    ensure_json_file(rules_path, DEFAULT_GMAIL_RULES)
    ensure_json_file(history_path, {"runs": []})

    app = GmailOrganizerApp(
        rules_path=rules_path,
        history_path=history_path,
        credentials_path=credentials_path,
        token_path=token_path,
    )
    app.mainloop()


if __name__ == "__main__":
    main()

