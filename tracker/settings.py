"""Configuration from environment variables / .env. No secrets live in code."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIR / ".env")


def _resolve(path_value: str) -> Path:
    path = Path(path_value).expanduser()
    return path if path.is_absolute() else PROJECT_DIR / path


def data_file() -> Path:
    """The spreadsheet to use: CASES_FILE if set, else cases.xlsx, else cases.csv."""
    configured = os.getenv("CASES_FILE")
    if configured:
        return _resolve(configured)
    xlsx = PROJECT_DIR / "cases.xlsx"
    csv = PROJECT_DIR / "cases.csv"
    return csv if csv.exists() and not xlsx.exists() else xlsx


OUTPUT_DIR = _resolve(os.getenv("OUTPUT_DIR", "output"))
LOG_FILE = _resolve(os.getenv("LOG_FILE", "logs/tracker.log"))
FIRM_NAME = os.getenv("FIRM_NAME", "Our Immigration Law Firm")
# When set, every alert email goes to this one address instead of the attorneys (for testing/demos).
REDIRECT_TO = os.getenv("REDIRECT_ALL_EMAILS_TO", "").strip()


@dataclass
class SmtpSettings:
    host: str
    port: int
    username: str
    password: str
    sender: str
    use_ssl: bool
    use_starttls: bool

    @property
    def is_configured(self) -> bool:
        return bool(self.host and self.sender)


def smtp_settings() -> SmtpSettings:
    return SmtpSettings(
        host=os.getenv("SMTP_HOST", ""),
        port=int(os.getenv("SMTP_PORT", "587")),
        username=os.getenv("SMTP_USERNAME", ""),
        password=os.getenv("SMTP_PASSWORD", ""),
        sender=os.getenv("SMTP_FROM", ""),
        use_ssl=os.getenv("SMTP_USE_SSL", "false").lower() == "true",
        use_starttls=os.getenv("SMTP_USE_STARTTLS", "true").lower() == "true",
    )


def setup_logging() -> logging.Logger:
    """Log to logs/tracker.log (and the console). Safe to call more than once."""
    logger = logging.getLogger("tracker")
    if logger.handlers:
        return logger
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(file_handler)
    logger.addHandler(console)
    logger.setLevel(logging.INFO)
    return logger
