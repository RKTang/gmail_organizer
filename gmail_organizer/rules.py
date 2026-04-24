from __future__ import annotations


def pick_label(subject: str, sender: str, snippet: str, config: dict) -> str:
    haystack = f"{subject} {sender} {snippet}".lower()
    for rule in config.get("rules", []):
        keywords = [token.lower() for token in rule.get("match", [])]
        if any(keyword in haystack for keyword in keywords):
            return str(rule.get("label", config.get("default_label", "To-Review")))
    return str(config.get("default_label", "To-Review"))

