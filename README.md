## Gmail Organizer App

A second desktop app is included to organize Gmail using rules, with preview-first behavior.

### Gmail Features

- Connect via Gmail OAuth
- Preview label/archive actions before applying
- Apply labels by keyword rules
- Optional selective auto-archive toggle (remove `INBOX` only for chosen labels)
- Undo the most recent run

### Gmail Setup

1. Install dependencies:

```bash
python -m pip install -r requirements.txt
```

2. Create a Google Cloud OAuth Desktop App and download the client JSON.
3. Save the JSON as `data/gmail_credentials.json`.
4. Launch:

```bash
python gmail_app.py
```

At first run, a browser window opens for Gmail permission consent.

### Gmail Config

Rules are in `data/gmail_rules.json`.

Example keys:

- `query`: Gmail search query target
- `max_results`: number of emails scanned per run
- `auto_archive`: enables archive behavior
- `auto_archive_labels`: labels allowed to auto-archive from inbox
- `rules`: keyword -> label mapping
- `default_label`: fallback label

### Recommended Auto-Archive Policy

- `auto_archive = true` for: `Newsletters`, `Shopping`, and low-risk notification labels
- keep in inbox (`auto_archive` excluded): `School`, `Finance`, `Jobs`, `To-Review`
- keep `default_label` as `To-Review` for uncertain emails

### Run In Background (Windows Task Scheduler)

Use the headless runner so you do not need to keep the app open:

```bash
python gmail_run_once.py
```

Create a scheduled task every 2-4 hours:

```powershell
powershell -ExecutionPolicy Bypass -File .\schedule_gmail_task.ps1 -EveryHours 3
```

Notes:

- set `-EveryHours` to `2`, `3`, or `4`
- first run `gmail_app.py` once to create `data/gmail_token.json`
- Task Scheduler executes `gmail_run_once.py` without the UI

