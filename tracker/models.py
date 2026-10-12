"""Plain data types used throughout the tracker."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Urgency(Enum):
    # Declared most-urgent first; that order is used for sorting and display.
    OVERDUE = "OVERDUE"
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    UPCOMING = "UPCOMING"
    OK = "OK"

    @property
    def rank(self) -> int:
        return list(Urgency).index(self)

    @property
    def description(self) -> str:
        return URGENCY_STYLE[self]["description"]

    @property
    def color(self) -> str:
        return URGENCY_STYLE[self]["color"]

    @property
    def background(self) -> str:
        return URGENCY_STYLE[self]["background"]

    @property
    def icon(self) -> str:
        return URGENCY_STYLE[self]["icon"]


URGENCY_STYLE = {
    Urgency.OVERDUE: {"description": "Past due", "color": "#b91c1c", "background": "#fee2e2", "icon": "🔴"},
    Urgency.CRITICAL: {"description": "Due in 0–2 days", "color": "#c2410c", "background": "#ffedd5", "icon": "🟠"},
    Urgency.WARNING: {"description": "Due in 3–7 days", "color": "#a16207", "background": "#fef9c3", "icon": "🟡"},
    Urgency.UPCOMING: {"description": "Due in 8–30 days", "color": "#1d4ed8", "background": "#dbeafe", "icon": "🔵"},
    Urgency.OK: {"description": "Due in more than 30 days", "color": "#15803d", "background": "#dcfce7", "icon": "🟢"},
}

# Urgency levels that trigger an attorney alert email.
ALERT_LEVELS = (Urgency.OVERDUE, Urgency.CRITICAL, Urgency.WARNING)


@dataclass
class Case:
    case_id: str
    client_name: str
    case_type: str
    status: str
    deadline: date
    deadline_type: str
    attorney: str
    attorney_email: str
    # Filled in by urgency.assess(); depends on "today", so not part of the source data.
    days_left: int = 0
    urgency: Urgency = Urgency.OK


@dataclass
class Issue:
    """A row that could not be tracked, with the reasons why."""

    row_number: int  # As the user sees it in the spreadsheet (header is row 1).
    case_id: str
    client_name: str
    problems: list[str]
    raw: dict = field(default_factory=dict)


@dataclass
class LoadResult:
    cases: list[Case]
    issues: list[Issue]
    source_name: str
    rows_read: int
