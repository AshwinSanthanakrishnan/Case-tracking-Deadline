import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from tracker.alerts import build_alerts
from tracker.data_source import COLUMNS, SpreadsheetSource, load_cases, parse_date, suggest_case_id
from tracker.models import Urgency

TODAY = date(2026, 10, 12)


def row(case_id, deadline, attorney="Maria Delgado", email="maria@example.com"):
    return {"Case ID": case_id, "Client Name": f"Client {case_id}", "Case Type": "I-485",
            "Current Status": "Open", "Next Deadline": deadline, "Deadline Type": "Filing deadline",
            "Assigned Attorney": attorney, "Attorney Email": email}


class DataSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write_csv(self, rows) -> SpreadsheetSource:
        path = Path(self.tmp.name) / "cases.csv"
        pd.DataFrame(rows, columns=list(COLUMNS)).to_csv(path, index=False)
        return SpreadsheetSource(path)

    def test_bad_rows_go_to_needs_attention(self):
        source = self.write_csv([
            row("A-1", "2026-10-10"),
            row("A-2", ""),                                  # missing date
            row("A-3", "next week"),                         # invalid date
            row("A-4", "2026-10-20", attorney="", email=""),  # no attorney
            row("A-5", "10/15/2026", email="not-an-email"),   # bad email
            row("A-1", "2026-11-01"),                        # duplicate ID
        ])
        result = load_cases(source, today=TODAY)
        self.assertEqual([c.case_id for c in result.cases], ["A-1"])
        self.assertEqual(result.cases[0].urgency, Urgency.OVERDUE)
        problems = {i.row_number: " ".join(i.problems) for i in result.issues}
        self.assertIn("Missing Next Deadline", problems[3])
        self.assertIn("Invalid Next Deadline", problems[4])
        self.assertIn("Missing Assigned Attorney", problems[5])
        self.assertIn("Invalid Attorney Email", problems[6])
        self.assertIn("Duplicate Case ID", problems[7])

    def test_add_and_update_round_trip_xlsx(self):
        path = Path(self.tmp.name) / "cases.xlsx"
        pd.DataFrame([row("A-1", date(2026, 10, 20))], columns=list(COLUMNS)).to_excel(path, index=False)
        source = SpreadsheetSource(path)
        source.add_case(row("A-2", date(2026, 12, 1)))
        source.update_case("A-1", {"Current Status": "Filed", "Next Deadline": date(2026, 10, 13)})
        result = load_cases(source, today=TODAY)
        self.assertEqual(result.issues, [])
        first = result.cases[0]
        self.assertEqual((first.case_id, first.status, first.urgency), ("A-1", "Filed", Urgency.CRITICAL))
        self.assertEqual(result.cases[1].deadline, date(2026, 12, 1))

    def test_alerts_only_include_urgent_cases(self):
        source = self.write_csv([
            row("A-1", "2026-10-11"),                                   # overdue
            row("A-2", "2026-11-30"),                                   # OK -> not emailed
            row("B-1", "2026-12-30", "James Okafor", "james@example.com"),  # only OK cases -> no email
        ])
        os.environ.pop("ANTHROPIC_API_KEY", None)
        alerts = build_alerts(load_cases(source, today=TODAY).cases, TODAY)
        self.assertEqual(len(alerts), 1)
        self.assertEqual([c.case_id for c in alerts[0].cases], ["A-1"])
        self.assertEqual(alerts[0].intro_source, "template")

    def test_parse_date_formats(self):
        self.assertEqual(parse_date("2026-10-12"), TODAY)
        self.assertEqual(parse_date("10/12/2026"), TODAY)
        self.assertIsNone(parse_date("TBD"))
        self.assertIsNone(parse_date("1926-10-12"))

    def test_suggest_case_id(self):
        self.assertEqual(suggest_case_id(["IMM-2026-009", "IMM-2026-017"]), "IMM-2026-018")
        self.assertEqual(suggest_case_id([]), "CASE-001")


if __name__ == "__main__":
    unittest.main()
