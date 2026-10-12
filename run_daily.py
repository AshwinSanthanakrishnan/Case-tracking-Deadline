"""Morning run: read cases, write the HTML report, and email each attorney their alerts.

    python run_daily.py                 # dry run (default): emails saved to output/emails/
    python run_daily.py --no-dry-run    # actually send via SMTP settings in .env
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from tracker import settings
from tracker.alerts import build_alerts, send_alerts, write_dry_run
from tracker.data_source import get_source, load_cases
from tracker.intro import ai_enabled
from tracker.models import ALERT_LEVELS
from tracker.report import write_report


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily immigration case deadline tracker")
    parser.add_argument("--data", help="Path to cases .xlsx or .csv (default: CASES_FILE or cases.xlsx)")
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write emails to output/emails instead of sending (default: on). Use --no-dry-run to send.",
    )
    parser.add_argument("--no-ai", action="store_true", help="Use the template intro even if ANTHROPIC_API_KEY is set")
    parser.add_argument("--today", type=date.fromisoformat, help="Pretend today is YYYY-MM-DD (for testing)")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    log = settings.setup_logging()
    today = args.today or date.today()
    log.info("=== Run started for %s (%s) ===", today, "dry run" if args.dry_run else "LIVE send")

    try:
        result = load_cases(get_source(args.data), today=today)
    except (FileNotFoundError, ValueError) as exc:
        log.error("Could not load cases: %s", exc)
        return 1

    flagged = [c for c in result.cases if c.urgency in ALERT_LEVELS]
    log.info(
        "Read %d rows from %s: %d valid, %d flagged (overdue/critical/warning), %d skipped",
        result.rows_read, result.source_name, len(result.cases), len(flagged), len(result.issues),
    )
    for issue in result.issues:
        log.warning("Skipped row %d (%s): %s", issue.row_number, issue.case_id or "no Case ID", "; ".join(issue.problems))

    report_path = write_report(result, today)
    log.info("Report written: %s", report_path)

    use_ai = not args.no_ai
    log.info("Email intros: %s", "Claude API" if use_ai and ai_enabled() else "template")
    alerts = build_alerts(result.cases, today, use_ai=use_ai)
    ai_count = sum(1 for a in alerts if a.intro_source == "claude")
    log.info("Generated %d attorney email(s) (%d with Claude intros)", len(alerts), ai_count)

    exit_code = 0
    if args.dry_run:
        folder = write_dry_run(alerts, today)
        log.info("Dry run: emails saved to %s (nothing sent)", folder)
    elif alerts:
        if settings.REDIRECT_TO:
            log.info("REDIRECT_ALL_EMAILS_TO is set: all alerts go to %s, no attorney is emailed", settings.REDIRECT_TO)
        try:
            sent, failed = send_alerts(alerts, settings.smtp_settings(), redirect_to=settings.REDIRECT_TO)
            log.info("Emails sent: %d, failed: %d", sent, failed)
            exit_code = 1 if failed else 0
        except (RuntimeError, OSError) as exc:  # OSError covers smtplib connection/auth errors
            log.error("Sending failed: %s", exc)
            exit_code = 1

    log.info("=== Run finished ===")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
