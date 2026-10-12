"""Deadline urgency rules. Pure functions, no I/O."""

from __future__ import annotations

from datetime import date

from .models import Case, Urgency


def classify(deadline: date, today: date) -> Urgency:
    """Map a deadline to an urgency level relative to today.

    OVERDUE  < 0 days
    CRITICAL 0–2 days
    WARNING  3–7 days
    UPCOMING 8–30 days
    OK       31+ days
    """
    days = (deadline - today).days
    if days < 0:
        return Urgency.OVERDUE
    if days <= 2:
        return Urgency.CRITICAL
    if days <= 7:
        return Urgency.WARNING
    if days <= 30:
        return Urgency.UPCOMING
    return Urgency.OK


def assess(cases: list[Case], today: date) -> list[Case]:
    """Set days_left/urgency on each case and return them most urgent first."""
    for case in cases:
        case.days_left = (case.deadline - today).days
        case.urgency = classify(case.deadline, today)
    return sorted(cases, key=lambda c: (c.urgency.rank, c.deadline, c.client_name))


def describe_days(days_left: int) -> str:
    if days_left < 0:
        n = -days_left
        return f"{n} day{'s' if n != 1 else ''} overdue"
    if days_left == 0:
        return "Due today"
    if days_left == 1:
        return "Due tomorrow"
    return f"Due in {days_left} days"
