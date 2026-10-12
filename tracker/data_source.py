"""Where case data comes from — the only module that knows about spreadsheets.

Everything else calls load_cases() (and, for the web app, add_case/update_case
on the source). To switch to a case management system, write a class with the
same three methods as SpreadsheetSource (read_rows, add_case, update_case) and
return it from get_source(). See "Replacing the data source" in the README.
"""

from __future__ import annotations

import re
from copy import copy
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from . import settings
from .models import Case, Issue, LoadResult
from .urgency import assess

# Spreadsheet header -> Case attribute.
COLUMNS = {
    "Case ID": "case_id",
    "Client Name": "client_name",
    "Case Type": "case_type",
    "Current Status": "status",
    "Next Deadline": "deadline",
    "Deadline Type": "deadline_type",
    "Assigned Attorney": "attorney",
    "Attorney Email": "attorney_email",
}
REQUIRED = ["Case ID", "Client Name", "Next Deadline", "Assigned Attorney", "Attorney Email"]
DATE_COLUMN = "Next Deadline"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DATE_FORMATS = ("%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%d %b %Y", "%b %d, %Y", "%B %d, %Y")


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def get_source(path: str | Path | None = None) -> "SpreadsheetSource":
    """Return the configured case source. Swap this for a CMS-backed source later."""
    return SpreadsheetSource(Path(path) if path else settings.data_file())


def load_cases(source=None, today: date | None = None) -> LoadResult:
    """Read every row, split into valid cases (sorted most urgent first) and issues."""
    source = source or get_source()
    today = today or date.today()
    rows = source.read_rows()

    cases: list[Case] = []
    issues: list[Issue] = []
    seen_ids: dict[str, int] = {}
    for row_number, row in rows:
        result = validate_row(row, row_number)
        if isinstance(result, Case):
            if result.case_id in seen_ids:
                issues.append(_issue(row, row_number, [f"Duplicate Case ID (also on row {seen_ids[result.case_id]})"]))
                continue
            seen_ids[result.case_id] = row_number
            cases.append(result)
        else:
            issues.append(result)

    return LoadResult(cases=assess(cases, today), issues=issues, source_name=source.name, rows_read=len(rows))


def validate_row(row: dict, row_number: int) -> Case | Issue:
    """Turn one raw row into a Case, or an Issue listing everything wrong with it."""
    values = {col: _clean(row.get(col)) for col in COLUMNS}
    problems = [f"Missing {col}" for col in REQUIRED if col != DATE_COLUMN and not values[col]]

    deadline = None
    raw_deadline = row.get(DATE_COLUMN)
    if _clean(raw_deadline) == "":
        problems.append(f"Missing {DATE_COLUMN}")
    else:
        deadline = parse_date(raw_deadline)
        if deadline is None:
            problems.append(f"Invalid {DATE_COLUMN}: {_clean(raw_deadline)!r}")

    email = values["Attorney Email"]
    if email and not _EMAIL_RE.match(email):
        problems.append(f"Invalid Attorney Email: {email!r}")

    if problems:
        return _issue(row, row_number, problems)

    fields = {attr: values[col] for col, attr in COLUMNS.items() if col != DATE_COLUMN}
    return Case(deadline=deadline, **fields)


def parse_date(value) -> date | None:
    """Accept real dates (from Excel) or common text formats (from CSV)."""
    if value is None or (isinstance(value, float) and pd.isna(value)) or value is pd.NaT:
        return None
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    else:
        text = str(value).strip()
        parsed = None
        try:
            parsed = datetime.fromisoformat(text).date()
        except ValueError:
            for fmt in _DATE_FORMATS:
                try:
                    parsed = datetime.strptime(text, fmt).date()
                    break
                except ValueError:
                    continue
    # Catch obvious typos such as 2206 or 1926.
    if parsed is None or not 2000 <= parsed.year <= 2100:
        return None
    return parsed


def suggest_case_id(existing_ids: list[str]) -> str:
    """Next ID in the firm's PREFIX-NNN style, based on the highest existing number."""
    best_prefix, best_num, width = "CASE-", 0, 3
    for case_id in existing_ids:
        match = re.match(r"^(.*?)(\d+)$", case_id)
        if match and int(match.group(2)) >= best_num:
            best_prefix, best_num, width = match.group(1), int(match.group(2)), len(match.group(2))
    return f"{best_prefix}{best_num + 1:0{width}d}"


# --------------------------------------------------------------------------- #
# Spreadsheet implementation (.xlsx or .csv)
# --------------------------------------------------------------------------- #

class SpreadsheetSource:
    def __init__(self, path: Path):
        self.path = Path(path)
        if self.path.suffix.lower() not in (".xlsx", ".csv"):
            raise ValueError(f"Unsupported file type {self.path.suffix!r}; use .xlsx or .csv")

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def is_excel(self) -> bool:
        return self.path.suffix.lower() == ".xlsx"

    def read_rows(self) -> list[tuple[int, dict]]:
        """Return (spreadsheet row number, {column: raw value}) for each non-blank row."""
        if not self.path.exists():
            raise FileNotFoundError(f"Case file not found: {self.path}")
        if self.is_excel:
            df = pd.read_excel(self.path, dtype=object, engine="openpyxl")
        else:
            df = pd.read_csv(self.path, dtype=str, keep_default_na=False)
        df.columns = [str(c).strip() for c in df.columns]
        missing = [c for c in COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"{self.name} is missing column(s): {', '.join(missing)}")

        rows = []
        for index, record in enumerate(df.to_dict(orient="records")):
            if all(_clean(v) == "" for v in record.values()):
                continue
            rows.append((index + 2, record))  # +2: header is row 1, data starts at row 2
        return rows

    def add_case(self, record: dict) -> None:
        """Append one case. `record` is keyed by spreadsheet column name."""
        if self.is_excel:
            wb, ws, header = self._open_sheet()
            new_row = _last_used_row(ws) + 1
            for col_name, col_idx in header.items():
                cell = ws.cell(row=new_row, column=col_idx)
                if new_row > 2:  # Copy formatting from the row above so the sheet stays tidy.
                    above = ws.cell(row=new_row - 1, column=col_idx)
                    cell.font, cell.fill, cell.border = copy(above.font), copy(above.fill), copy(above.border)
                    cell.alignment, cell.number_format = copy(above.alignment), above.number_format
                self._set_cell(cell, col_name, record.get(col_name, ""))
            wb.save(self.path)
        else:
            df = pd.read_csv(self.path, dtype=str, keep_default_na=False)
            row = {c: _to_text(record.get(c, "")) for c in df.columns}
            pd.concat([df, pd.DataFrame([row])], ignore_index=True).to_csv(self.path, index=False)

    def update_case(self, case_id: str, changes: dict) -> None:
        """Change some columns of the row with this Case ID."""
        if self.is_excel:
            wb, ws, header = self._open_sheet()
            id_col = header["Case ID"]
            for r in range(2, ws.max_row + 1):
                if _clean(ws.cell(row=r, column=id_col).value) == case_id:
                    for col_name, value in changes.items():
                        self._set_cell(ws.cell(row=r, column=header[col_name]), col_name, value)
                    wb.save(self.path)
                    return
        else:
            df = pd.read_csv(self.path, dtype=str, keep_default_na=False)
            match = df["Case ID"].str.strip() == case_id
            if match.any():
                for col_name, value in changes.items():
                    df.loc[match, col_name] = _to_text(value)
                df.to_csv(self.path, index=False)
                return
        raise KeyError(f"Case ID {case_id!r} not found in {self.name}")

    def _open_sheet(self):
        from openpyxl import load_workbook

        wb = load_workbook(self.path)
        ws = wb.active
        header = {str(c.value).strip(): c.column for c in ws[1] if c.value is not None}
        return wb, ws, header

    @staticmethod
    def _set_cell(cell, col_name: str, value) -> None:
        if col_name == DATE_COLUMN and isinstance(value, date):
            cell.value = value if not isinstance(value, datetime) else value.date()
            cell.number_format = "yyyy-mm-dd"
        else:
            cell.value = _to_text(value)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _clean(value) -> str:
    """Normalise a raw cell to a trimmed string ('' for blanks/NaN)."""
    if value is None:
        return ""
    if isinstance(value, float):
        if pd.isna(value):
            return ""
        if value.is_integer():  # Excel turns 101 into 101.0
            return str(int(value))
    if value is pd.NaT:
        return ""
    return str(value).strip()


def _to_text(value) -> str:
    if isinstance(value, datetime):
        value = value.date()
    return value.isoformat() if isinstance(value, date) else _clean(value)


def _issue(row: dict, row_number: int, problems: list[str]) -> Issue:
    return Issue(
        row_number=row_number,
        case_id=_clean(row.get("Case ID")),
        client_name=_clean(row.get("Client Name")),
        problems=problems,
        raw={k: _to_text(v) for k, v in row.items()},
    )


def _last_used_row(ws) -> int:
    for r in range(ws.max_row, 1, -1):
        if any(c.value not in (None, "") for c in ws[r]):
            return r
    return 1
