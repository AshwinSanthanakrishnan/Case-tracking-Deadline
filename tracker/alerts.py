"""Per-attorney alert emails: build, preview (dry run) or send via SMTP."""

from __future__ import annotations

import logging
import re
import smtplib
from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage
from html import escape
from pathlib import Path

from . import settings
from .intro import write_intro
from .models import ALERT_LEVELS, Case
from .urgency import describe_days

log = logging.getLogger("tracker")

DRY_RUN_SENDER = "Deadline Tracker <deadline-tracker@example.com>"


@dataclass
class AttorneyAlert:
    attorney: str
    email: str
    cases: list[Case]  # Only OVERDUE / CRITICAL / WARNING, most urgent first.
    intro: str
    intro_source: str  # "claude" or "template"
    subject: str
    text_body: str
    html_body: str


def build_alerts(cases: list[Case], today: date, use_ai: bool = True) -> list[AttorneyAlert]:
    """One alert per attorney who has at least one OVERDUE/CRITICAL/WARNING case."""
    by_email: dict[str, list[Case]] = {}
    for case in cases:  # Already sorted most urgent first.
        if case.urgency in ALERT_LEVELS:
            by_email.setdefault(case.attorney_email.lower(), []).append(case)

    alerts = []
    for email, their_cases in sorted(by_email.items(), key=lambda kv: kv[1][0].attorney):
        attorney = their_cases[0].attorney
        intro, source = write_intro(attorney, their_cases, today, use_ai=use_ai)
        alerts.append(
            AttorneyAlert(
                attorney=attorney,
                email=their_cases[0].attorney_email,
                cases=their_cases,
                intro=intro,
                intro_source=source,
                subject=_subject(their_cases, today),
                text_body=_text_body(attorney, intro, their_cases),
                html_body=_html_body(attorney, intro, their_cases),
            )
        )
    return alerts


def to_message(alert: AttorneyAlert, sender: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = alert.subject
    msg["From"] = sender
    msg["To"] = alert.email
    msg.set_content(alert.text_body)
    msg.add_alternative(alert.html_body, subtype="html")
    return msg


def write_dry_run(alerts: list[AttorneyAlert], today: date, out_dir: Path | None = None) -> Path:
    """Save each email as .eml (opens in any mail app) plus .html for quick viewing."""
    folder = (out_dir or settings.OUTPUT_DIR) / "emails" / f"{today:%Y-%m-%d}"
    folder.mkdir(parents=True, exist_ok=True)
    for old in list(folder.glob("*.eml")) + list(folder.glob("*.html")):
        old.unlink()  # Re-running the same day replaces that day's previews.
    sender = settings.smtp_settings().sender or DRY_RUN_SENDER
    for alert in alerts:
        slug = re.sub(r"[^a-z0-9]+", "_", alert.attorney.lower()).strip("_") or "attorney"
        (folder / f"{slug}.eml").write_bytes(bytes(to_message(alert, sender)))
        (folder / f"{slug}.html").write_text(alert.html_body, encoding="utf-8")
    return folder


def send_alerts(alerts: list[AttorneyAlert], smtp: settings.SmtpSettings, redirect_to: str = "") -> tuple[int, int]:
    """Send over SMTP. Returns (sent, failed); one bad address doesn't stop the rest.

    With redirect_to set, every alert goes to that one address instead of the attorneys.
    """
    sent = failed = 0
    with _connect(smtp) as server:
        for alert in alerts:
            msg = to_message(alert, smtp.sender)
            if redirect_to:
                msg.replace_header("To", redirect_to)
                msg.replace_header("Subject", f"[For {alert.attorney}] {alert.subject}")
            recipient = msg["To"]
            try:
                server.send_message(msg)
                sent += 1
                log.info("Sent %s's alert (%d cases) to %s", alert.attorney, len(alert.cases), recipient)
            except smtplib.SMTPException as exc:
                failed += 1
                log.error("Failed to send %s's alert to %s: %s", alert.attorney, recipient, exc)
    return sent, failed


def send_test(alert: AttorneyAlert, to_address: str, smtp: settings.SmtpSettings) -> None:
    """Send one attorney's alert to another address (e.g. your own) to check email works."""
    msg = to_message(alert, smtp.sender)
    msg.replace_header("To", to_address)
    msg.replace_header("Subject", f"[TEST copy of {alert.attorney}'s alert] {alert.subject}")
    with _connect(smtp) as server:
        server.send_message(msg)
    log.info("Sent TEST copy of %s's alert to %s", alert.attorney, to_address)


def _connect(smtp: settings.SmtpSettings) -> smtplib.SMTP:
    if not smtp.is_configured:
        raise RuntimeError("SMTP is not configured. Set SMTP_HOST and SMTP_FROM in .env, or use --dry-run.")
    server_cls = smtplib.SMTP_SSL if smtp.use_ssl else smtplib.SMTP
    server = server_cls(smtp.host, smtp.port, timeout=30)
    try:
        if smtp.use_starttls and not smtp.use_ssl:
            server.starttls()
        if smtp.username:
            server.login(smtp.username, smtp.password)
    except BaseException:
        server.close()
        raise
    return server


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #

def _subject(cases: list[Case], today: date) -> str:
    parts = []
    for level in ALERT_LEVELS:
        n = sum(1 for c in cases if c.urgency is level)
        if n:
            parts.append(f"{n} {level.value.lower()}")
    return f"Deadline alert {today:%b %d}: {', '.join(parts)}"


def _first_name(attorney: str) -> str:
    return attorney.split()[0] if attorney.split() else attorney


def _text_body(attorney: str, intro: str, cases: list[Case]) -> str:
    lines = [f"Hi {_first_name(attorney)},", "", intro, ""]
    for level in ALERT_LEVELS:
        group = [c for c in cases if c.urgency is level]
        if not group:
            continue
        lines.append(f"{level.value} ({len(group)})")
        for c in group:
            lines.append(
                f"  - {c.case_id} | {c.client_name} | {c.case_type} | {c.deadline_type} | "
                f"{c.deadline:%b %d, %Y} ({describe_days(c.days_left)}) | Status: {c.status}"
            )
        lines.append("")
    lines += ["This is an automated message from the case deadline tracker."]
    return "\n".join(lines)


def _html_body(attorney: str, intro: str, cases: list[Case]) -> str:
    rows = "".join(
        f'<tr style="background:{c.urgency.background}">'
        f'<td style="padding:6px 8px;color:{c.urgency.color};font-weight:700">{c.urgency.value}</td>'
        f'<td style="padding:6px 8px;color:#1f2937">{escape(c.case_id)}</td>'
        f'<td style="padding:6px 8px;color:#1f2937">{escape(c.client_name)}</td>'
        f'<td style="padding:6px 8px;color:#1f2937">{escape(c.case_type)}</td>'
        f'<td style="padding:6px 8px;color:#1f2937">{escape(c.deadline_type)}</td>'
        f'<td style="padding:6px 8px;color:#1f2937;white-space:nowrap">{c.deadline:%b %d, %Y}<br>'
        f'<small>{describe_days(c.days_left)}</small></td>'
        f'<td style="padding:6px 8px;color:#1f2937">{escape(c.status)}</td></tr>'
        for c in cases
    )
    th = 'style="text-align:left;padding:6px 8px;background:#f1f5f9;color:#475569;font-size:12px"'
    return f"""<!doctype html>
<html><body style="margin:0"><div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1f2937;background:#ffffff;font-size:14px;padding:16px">
<p>Hi {escape(_first_name(attorney))},</p>
<p>{escape(intro)}</p>
<table style="border-collapse:collapse;width:100%;max-width:900px">
<tr><th {th}>Urgency</th><th {th}>Case ID</th><th {th}>Client</th><th {th}>Case type</th>
<th {th}>Deadline type</th><th {th}>Deadline</th><th {th}>Status</th></tr>
{rows}
</table>
<p style="color:#64748b;font-size:12px">This is an automated message from the case deadline tracker.</p>
</div></body></html>"""
