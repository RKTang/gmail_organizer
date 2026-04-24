from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
from typing import Any, Callable

from .gmail_client import (
    batch_modify_messages,
    get_message_meta,
    get_or_create_label_ids,
    list_message_ids,
    list_user_labels,
    modify_message_labels,
)
from .history import MessageChange, append_run, load_last_run
from .rules import pick_label


@dataclass
class PlannedEmailAction:
    message_id: str
    subject: str
    sender: str
    add_label_name: str
    add_label_id: str | None
    existing_label_ids: list[str]
    remove_label_ids: list[str]


@dataclass
class PlanStats:
    processed: int
    skipped: int
    labeled: int


def build_plan(
    service: Any,
    config: dict,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> tuple[list[PlannedEmailAction], PlanStats]:
    # Always target latest inbox emails and cap by max_results.
    query = "in:inbox"
    max_results = int(config.get("max_results", 200))
    auto_archive = bool(config.get("auto_archive", False))
    auto_archive_labels = {str(item).strip() for item in config.get("auto_archive_labels", []) if str(item).strip()}
    user_label_map = list_user_labels(service)
    label_id_to_name = {label_id: name for name, label_id in user_label_map.items()}

    message_ids = list_message_ids(service, query=query, max_results=max_results)
    plan: list[PlannedEmailAction] = []
    skipped = 0

    total = len(message_ids)
    if on_progress is not None:
        on_progress(0, total, "Fetching message details")

    for index, message_id in enumerate(message_ids, start=1):
        meta = get_message_meta(service, message_id)

        # Skip messages that already have any user-created label.
        existing_user_label_names = [
            label_id_to_name[label_id]
            for label_id in meta.label_ids
            if label_id in label_id_to_name
        ]
        has_user_label = bool(existing_user_label_names)
        if has_user_label:
            remove_label_ids: list[str] = []
            should_archive_labeled = bool(auto_archive_labels.intersection(existing_user_label_names))
            if auto_archive and should_archive_labeled and "INBOX" in meta.label_ids:
                remove_label_ids.append("INBOX")
                plan.append(
                    PlannedEmailAction(
                        message_id=meta.message_id,
                        subject=meta.subject,
                        sender=meta.sender,
                        add_label_name="",
                        add_label_id=None,
                        existing_label_ids=meta.label_ids,
                        remove_label_ids=remove_label_ids,
                    )
                )
            else:
                skipped += 1
            if on_progress is not None:
                on_progress(index, total, "Skipping already labeled emails")
            continue

        label_name = pick_label(meta.subject, meta.sender, meta.snippet, config)

        remove_label_ids: list[str] = []
        should_archive_new = label_name in auto_archive_labels
        if auto_archive and should_archive_new and "INBOX" in meta.label_ids:
            remove_label_ids.append("INBOX")

        plan.append(
            PlannedEmailAction(
                message_id=meta.message_id,
                subject=meta.subject,
                sender=meta.sender,
                add_label_name=label_name,
                add_label_id=None,
                existing_label_ids=meta.label_ids,
                remove_label_ids=remove_label_ids,
            )
        )

        if on_progress is not None:
            on_progress(index, total, "Building preview plan")

    label_names = sorted({item.add_label_name for item in plan if item.add_label_name})
    label_ids = get_or_create_label_ids(service, label_names) if label_names else {}

    filtered: list[PlannedEmailAction] = []
    for item in plan:
        if item.add_label_name:
            label_id = label_ids.get(item.add_label_name)
            if not label_id:
                continue
            item.add_label_id = label_id
            if label_id not in item.existing_label_ids or item.remove_label_ids:
                filtered.append(item)
            continue

        # Already-labeled message in archive-only mode.
        if item.remove_label_ids:
            filtered.append(item)

    stats = PlanStats(processed=total, skipped=skipped, labeled=len(filtered))
    return filtered, stats


def apply_plan(
    service: Any,
    plan: list[PlannedEmailAction],
    history_path,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> int:
    changes: list[MessageChange] = []
    total = len(plan)
    if on_progress is not None:
        on_progress(0, total, "Applying changes")

    grouped_ids: dict[tuple[str | None, tuple[str, ...]], list[str]] = defaultdict(list)
    for item in plan:
        key = (item.add_label_id, tuple(item.remove_label_ids))
        grouped_ids[key].append(item.message_id)

    processed = 0
    for (add_label_id, remove_tuple), message_ids in grouped_ids.items():
        remove_label_ids = list(remove_tuple)
        for start in range(0, len(message_ids), 1000):
            chunk = message_ids[start : start + 1000]
            batch_modify_messages(
                service=service,
                message_ids=chunk,
                add_label_ids=[add_label_id] if add_label_id else [],
                remove_label_ids=remove_label_ids,
            )
            for message_id in chunk:
                changes.append(
                    MessageChange(
                        message_id=message_id,
                        added_label_ids=[add_label_id] if add_label_id else [],
                        removed_label_ids=remove_label_ids,
                    )
                )
            processed += len(chunk)
            if on_progress is not None:
                on_progress(processed, total, "Applying changes")

    if changes:
        append_run(history_path, changes)
    return len(changes)


def build_relabel_plan(
    service: Any,
    config: dict,
    source_label_name: str,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> tuple[list[PlannedEmailAction], PlanStats]:
    max_results = int(config.get("max_results", 200))
    source_label_name = source_label_name.strip()
    label_map = list_user_labels(service)
    source_label_id = label_map.get(source_label_name)
    if not source_label_id:
        return [], PlanStats(processed=0, skipped=0, labeled=0)

    message_ids = list_message_ids(
        service=service,
        query="",
        max_results=max_results,
        label_ids=[source_label_id],
    )
    total = len(message_ids)
    skipped = 0
    plan: list[PlannedEmailAction] = []
    if on_progress is not None:
        on_progress(0, total, f"Scanning label {source_label_name}")

    for index, message_id in enumerate(message_ids, start=1):
        meta = get_message_meta(service, message_id)
        new_label_name = pick_label(meta.subject, meta.sender, meta.snippet, config)
        if new_label_name == source_label_name:
            skipped += 1
        else:
            plan.append(
                PlannedEmailAction(
                    message_id=meta.message_id,
                    subject=meta.subject,
                    sender=meta.sender,
                    add_label_name=new_label_name,
                    add_label_id=None,
                    existing_label_ids=meta.label_ids,
                    remove_label_ids=[source_label_id],
                )
            )
        if on_progress is not None:
            on_progress(index, total, "Evaluating relabel candidates")

    target_names = sorted({item.add_label_name for item in plan if item.add_label_name})
    target_ids = get_or_create_label_ids(service, target_names) if target_names else {}
    filtered: list[PlannedEmailAction] = []
    for item in plan:
        label_id = target_ids.get(item.add_label_name)
        if not label_id or label_id == source_label_id:
            skipped += 1
            continue
        item.add_label_id = label_id
        filtered.append(item)

    return filtered, PlanStats(processed=total, skipped=skipped, labeled=len(filtered))


def undo_last_run(service: Any, history_path) -> int:
    changes = load_last_run(history_path)
    undone = 0
    for item in changes:
        modify_message_labels(
            service=service,
            message_id=item.message_id,
            add_label_ids=item.removed_label_ids,
            remove_label_ids=item.added_label_ids,
        )
        undone += 1
    return undone

