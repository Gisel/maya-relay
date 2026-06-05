from typing import Protocol

import requests

from app.config import Settings


AI_TRIAGE_MAX_CHARACTERS = 700


class MessageTriage(Protocol):
    def summarize(self, *, body: str, has_attachments: bool, conversation_code: str | None = None) -> str | None:
        ...


class NoopMessageTriage:
    def summarize(self, *, body: str, has_attachments: bool, conversation_code: str | None = None) -> str | None:
        return None


class OpenAIMessageTriage:
    def __init__(self, settings: Settings):
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when ENABLE_AI_TRIAGE=true.")
        self.api_key = settings.openai_api_key
        self.model = settings.openai_model

    def summarize(self, *, body: str, has_attachments: bool, conversation_code: str | None = None) -> str | None:
        if not body.strip() and not has_attachments:
            return None

        prompt_lines = [
            "Customer message:",
            body.strip() or "[No text body]",
            "",
            f"Has attachments: {'yes' if has_attachments else 'no'}",
        ]
        if conversation_code:
            prompt_lines.append(f"Conversation reply code: #{conversation_code}")
        prompt = "\n".join(prompt_lines)
        try:
            response = requests.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "instructions": (
                        "You triage inbound messages for Maya Graphics and Signs. "
                        "Write a concise internal SMS note for Francisco, not for the customer. "
                        "Use at most 3 short lines. Line 1: intent. Line 2: missing details. "
                        "Line 3: a short suggested reply only when useful. "
                        "If you include a suggested reply, start it with the exact conversation reply code. "
                        "Match the customer's language. Keep the whole note under 650 characters. "
                        "Business context: Maya has one location. Office hours are Monday-Friday 9:00 AM-6:00 PM. "
                        "Saturday is by appointment only. "
                        "Do not invent prices, commitments, timelines, or policies."
                    ),
                    "input": prompt,
                    "max_output_tokens": 500,
                    "reasoning": {"effort": "low"},
                    "text": {"verbosity": "low"},
                },
                timeout=12,
            )
            response.raise_for_status()
        except requests.RequestException:
            return None

        output_text = _extract_response_text(response.json())
        if output_text is None:
            return None

        summary = _compact_summary(output_text)
        return summary or None


def _extract_response_text(payload: dict) -> str | None:
    output_text = payload.get("output_text")
    if isinstance(output_text, str):
        return output_text

    parts: list[str] = []
    output = payload.get("output")
    if not isinstance(output, list):
        return None

    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for content_item in content:
            if not isinstance(content_item, dict):
                continue
            text = content_item.get("text")
            if isinstance(text, str):
                parts.append(text)

    text = "\n".join(parts).strip()
    return text or None


def _compact_summary(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    compact_lines = lines[:3]
    for index, line in enumerate(compact_lines):
        if index > 0 and line.startswith("#"):
            compact_lines.insert(index, "---")
            break
    return _trim_to_character_limit("\n".join(compact_lines), AI_TRIAGE_MAX_CHARACTERS)


def _trim_to_character_limit(text: str, max_characters: int) -> str:
    if len(text) <= max_characters:
        return text
    trimmed = text[: max_characters - 3].rstrip()
    if " " in trimmed:
        trimmed = trimmed.rsplit(" ", 1)[0]
    return f"{trimmed}..."
