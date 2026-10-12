import unittest
from datetime import date, timedelta

from tracker.models import Case, Urgency
from tracker.urgency import assess, classify, describe_days

TODAY = date(2026, 10, 12)


def in_days(n: int) -> date:
    return TODAY + timedelta(days=n)


def make_case(case_id: str, days: int) -> Case:
    return Case(case_id, f"Client {case_id}", "I-130", "Open", in_days(days), "Filing deadline",
                "Test Attorney", "attorney@example.com")


class ClassifyTests(unittest.TestCase):
    def test_boundaries(self):
        expected = {
            -30: Urgency.OVERDUE,
            -1: Urgency.OVERDUE,
            0: Urgency.CRITICAL,
            2: Urgency.CRITICAL,
            3: Urgency.WARNING,
            7: Urgency.WARNING,
            8: Urgency.UPCOMING,
            30: Urgency.UPCOMING,
            31: Urgency.OK,
            365: Urgency.OK,
        }
        for days, level in expected.items():
            with self.subTest(days=days):
                self.assertEqual(classify(in_days(days), TODAY), level)

    def test_assess_sorts_most_urgent_first(self):
        cases = [make_case("ok", 60), make_case("late", -3), make_case("soon", 5), make_case("today", 0),
                 make_case("later", -1)]
        ordered = assess(cases, TODAY)
        self.assertEqual([c.case_id for c in ordered], ["late", "later", "today", "soon", "ok"])
        self.assertEqual(ordered[0].days_left, -3)
        self.assertEqual(ordered[-1].urgency, Urgency.OK)

    def test_describe_days(self):
        self.assertEqual(describe_days(-1), "1 day overdue")
        self.assertEqual(describe_days(-4), "4 days overdue")
        self.assertEqual(describe_days(0), "Due today")
        self.assertEqual(describe_days(1), "Due tomorrow")
        self.assertEqual(describe_days(9), "Due in 9 days")


if __name__ == "__main__":
    unittest.main()
