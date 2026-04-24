from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


@dataclass
class MessageMeta:
    message_id: str
    thread_id: str
    subject: str
    sender: str
    snippet: str
    label_ids: list[str]


def build_service(credentials_path: Path, token_path: Path):
    creds: Credentials | None = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds is None or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds)


def get_or_create_label_id(service: Any, label_name: str) -> str:
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    for label in labels:
        if label.get("name") == label_name:
            return str(label.get("id"))
    created = (
        service.users()
        .labels()
        .create(
            userId="me",
            body={
                "name": label_name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            },
        )
        .execute()
    )
    return str(created.get("id"))


def get_or_create_label_ids(service: Any, label_names: list[str]) -> dict[str, str]:
    existing_labels = service.users().labels().list(userId="me").execute().get("labels", [])
    by_name: dict[str, str] = {
        str(label.get("name", "")): str(label.get("id", ""))
        for label in existing_labels
        if label.get("name") and label.get("id")
    }

    result: dict[str, str] = {}
    for name in label_names:
        if name in by_name:
            result[name] = by_name[name]
            continue

        created = (
            service.users()
            .labels()
            .create(
                userId="me",
                body={
                    "name": name,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                },
            )
            .execute()
        )
        created_id = str(created.get("id"))
        by_name[name] = created_id
        result[name] = created_id

    return result


def list_user_labels(service: Any) -> dict[str, str]:
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    return {
        str(label.get("name", "")): str(label.get("id", ""))
        for label in labels
        if label.get("type") == "user" and label.get("name") and label.get("id")
    }


def list_message_ids(
    service: Any,
    query: str,
    max_results: int,
    label_ids: list[str] | None = None,
) -> list[str]:
    max_results = max(1, int(max_results))
    message_ids: list[str] = []
    next_page_token: str | None = None

    # Gmail list endpoint is paginated; keep fetching until we hit max_results.
    while len(message_ids) < max_results:
        remaining = max_results - len(message_ids)
        page_size = min(500, remaining)
        request = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=page_size,
            pageToken=next_page_token,
            labelIds=label_ids or None,
        )
        result = request.execute()
        messages = result.get("messages", [])
        message_ids.extend(str(item["id"]) for item in messages if "id" in item)
        next_page_token = result.get("nextPageToken")
        if not next_page_token:
            break

    return message_ids[:max_results]


def _header(payload: dict, name: str) -> str:
    headers = payload.get("headers", [])
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return str(header.get("value", ""))
    return ""


def get_message_meta(service: Any, message_id: str) -> MessageMeta:
    data = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="metadata", metadataHeaders=["Subject", "From"])
        .execute()
    )
    payload = data.get("payload", {})
    return MessageMeta(
        message_id=message_id,
        thread_id=str(data.get("threadId", "")),
        subject=_header(payload, "Subject"),
        sender=_header(payload, "From"),
        snippet=str(data.get("snippet", "")),
        label_ids=[str(item) for item in data.get("labelIds", [])],
    )


def modify_message_labels(
    service: Any,
    message_id: str,
    add_label_ids: list[str],
    remove_label_ids: list[str],
) -> None:
    (
        service.users()
        .messages()
        .modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": add_label_ids, "removeLabelIds": remove_label_ids},
        )
        .execute()
    )


def batch_modify_messages(
    service: Any,
    message_ids: list[str],
    add_label_ids: list[str],
    remove_label_ids: list[str],
) -> None:
    if not message_ids:
        return
    (
        service.users()
        .messages()
        .batchModify(
            userId="me",
            body={
                "ids": message_ids,
                "addLabelIds": add_label_ids,
                "removeLabelIds": remove_label_ids,
            },
        )
        .execute()
    )


def decode_body_base64(value: str) -> str:
    raw = base64.urlsafe_b64decode(value + "===")
    return raw.decode("utf-8", errors="ignore")

