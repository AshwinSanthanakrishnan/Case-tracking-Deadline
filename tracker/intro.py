"""Opening paragraph for each attorney's alert email.

Uses Claude when ANTHROPIC_API_KEY is set; otherwise (or on any API problem)
falls back to a plain template, so the tracker never depends on the API.
Only counts, case types and deadline types are sent to the API — never client
names or case IDs.
"""

from __future__ import annotations

import logging
import os
from collections import Counter
from datetime import date

from .models import ALERT_LEVELS, Case

log = logging.getLogger("tracker")

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
SYSTEM_PROMPT = (
    "You write the opening paragraph of an internal daily deadline-alert email at an immigration law firm. "
    "Write 2-3 sentences of plain text in a calm, professional tone addressed to the attorney. "
    "Summarize what needs their attention today and what to prioritize, using only the facts provided. "
    "Do not include a greeting, sign-off, bullet points, markdown, or any case details beyond what you are given."
)

_client = None


def ai_enabled() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def write_intro(attorney: str, cases: list[Case], today: date, use_ai: bool = True) -> tuple[str, str]:
    """Return (paragraph, source) where source is 'claude' or 'template'."""
    if use_ai and ai_enabled():
        text = _claude_intro(attorney, cases, today)
        if text:
            return text, "claude"
    return template_intro(cases), "template"


def template_intro(cases: list[Case]) -> str:
    counts = Counter(c.urgency for c in cases)
    parts = [f"{counts[lvl]} {lvl.value.lower()}" for lvl in ALERT_LEVELS if counts[lvl]]
    summary = _join(parts)
    total = len(cases)
    text = f"You have {total} case{'s' if total != 1 else ''} needing attention today: {summary}."
    if counts[ALERT_LEVELS[0]]:
        text += " Please prioritize the overdue items first and confirm whether any filings or extensions are needed."
    else:
        text += " Please review the items below and confirm each deadline is on track."
    return text


def _claude_intro(attorney: str, cases: list[Case], today: date) -> str | None:
    import anthropic

    global _client
    if _client is None:
        # Short timeout so a slow API never holds up the morning run.
        _client = anthropic.Anthropic(timeout=30.0, max_retries=2)

    counts = Counter(c.urgency for c in cases)
    lines = [
        f"Attorney: {attorney}",
        f"Today: {today:%A, %B %d, %Y}",
        "Counts: " + ", ".join(f"{lvl.value} {counts[lvl]}" for lvl in ALERT_LEVELS),
        "Items (case type / deadline type / timing):",
    ]
    lines += [f"- {c.case_type} / {c.deadline_type} / {_timing(c.days_left)}" for c in cases]

    try:
        response = _client.beta.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            output_config={"effort": "low"},
            # If a request is declined, let the API retry it on a suitable fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": "\n".join(lines)}],
        )
    except anthropic.APIError as exc:
        log.warning("Claude intro failed for %s (%s: %s); using template", attorney, type(exc).__name__, exc)
        return None

    if response.stop_reason == "refusal":
        log.warning("Claude declined the intro for %s; using template", attorney)
        return None
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text or len(text) > 1200:
        log.warning("Claude intro for %s was empty or too long; using template", attorney)
        return None
    return text


def _timing(days_left: int) -> str:
    if days_left < 0:
        return f"{-days_left} days overdue"
    return "due today" if days_left == 0 else f"due in {days_left} days"


def _join(parts: list[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]
