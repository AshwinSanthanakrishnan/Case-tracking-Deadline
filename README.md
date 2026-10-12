# Case Deadline Tracker

A small deadline and case tracker for an immigration law firm. It reads cases from a spreadsheet, works out how urgent each deadline is, and gives you:

- **A daily HTML report** grouped by urgency and color-coded, with counts at the top.
- **One alert email per attorney** listing only their OVERDUE, CRITICAL, and WARNING cases. Dry run is on by default.
- **A web dashboard** for viewing, filtering, adding, and editing cases, and for previewing alert emails.

The scheduled morning script and the dashboard use the same code in `tracker/`, so they always agree.

| Urgency | Rule | Color |
|---|---|---|
| OVERDUE | deadline has passed | red |
| CRITICAL | due in 0–2 days | orange |
| WARNING | due in 3–7 days | yellow |
| UPCOMING | due in 8–30 days | blue |
| OK | due in 31+ days | green |

Rows with a missing or invalid date, a missing attorney or email, a missing Case ID or client name, or a duplicate Case ID are **skipped and listed under "Needs attention"**. They never crash the run.

---

## One-click demo (Mac)

Double-click **`Start Demo.command`** in Finder. It creates fresh fake cases in `demo/`, runs the morning job as a dry run, opens the daily report, and starts the dashboard at http://localhost:8501. Your real `cases.xlsx` is never touched and no attorney is emailed. Close the Terminal window to stop it.

If SMTP is set up in `.env`, the dashboard's **Attorney alerts** tab also has **Send a test copy to yourself**, so you can show a real email arriving. See [DEMO.md](DEMO.md) for a 5-minute presenter script.

---

## Install

You need Python 3.10 or newer.

```bash
cd "Case Tracking"
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
python make_sample_data.py         # creates cases.xlsx with 18 FAKE cases
```

`make_sample_data.py` sets deadlines relative to today, so run it again before a demo to make sure every urgency level appears. It writes 15 good rows and 3 deliberately broken ones so the "Needs attention" section has something to show. Use `--csv` to write `cases.csv` instead.

### Spreadsheet format

The first row must have these headers (in any order):

`Case ID · Client Name · Case Type · Current Status · Next Deadline · Deadline Type · Assigned Attorney · Attorney Email`

`Next Deadline` can be a real Excel date or text like `2026-10-15` or `10/15/2026`. If both `cases.xlsx` and `cases.csv` exist, the `.xlsx` file is used. To point at another file, set `CASES_FILE` in `.env` or pass `--data`.

---

## Run the morning script

```bash
python run_daily.py                 # dry run: report + emails written to output/, nothing sent
python run_daily.py --no-dry-run    # really send the emails via SMTP
```

Other options: `--data path/to/cases.csv`, `--no-ai` (always use the template intro), and `--today 2026-10-20` (pretend it's another day, useful for testing).

Each run produces:

- `output/reports/deadline_report_YYYY-MM-DD.html`: the daily summary.
- `output/emails/YYYY-MM-DD/<attorney>.eml` and `.html` (dry run only). The `.eml` files open in Mail or Outlook; the `.html` files open in a browser.
- `logs/tracker.log`: rows read, cases flagged, rows skipped (with reasons), emails generated or sent. Edits made in the dashboard are logged here too.

### Sending email

Fill in the `SMTP_*` settings in `.env` (host, port, username, password, from address). Credentials are only read from `.env` and never stored in code. If one address fails, the other emails still go out, and the failure is logged.

To test real sending safely, set `REDIRECT_ALL_EMAILS_TO=you@yourfirm.com` in `.env`. Every alert then goes to that one address, with the attorney's name in the subject, and no attorney is emailed. The one-click demo sends for real only when this is set. Clear it to email the attorneys normally.

### Optional: AI-written email intros

If `ANTHROPIC_API_KEY` is set in `.env`, Claude writes a short, professional opening paragraph for each attorney's email. If the key isn't set, or the API is slow, unavailable, or declines the request, the script falls back to a built-in template. The tool works fully without the API.

**Privacy:** only counts, case types, deadline types, and timing are sent to the API. Client names and case IDs are never sent. Those appear only in the email table, which is built locally.

---

## Run the web dashboard

```bash
streamlit run app.py
```

Then open <http://localhost:8501> in your browser. The app runs in headless mode (set in `.streamlit/config.toml`), so Streamlit won't open a browser tab or ask for an email on first launch. The dashboard has:

- **Counts at the top:** overdue, critical, due this week (0–7 days), total cases, and rows needing attention.
- **Sidebar filters:** urgency level, assigned attorney, and a client-name search. There is also a *Reload* button and a download link for today's HTML report.
- **Cases tab:** a color-coded table sorted most urgent first. Edit **Current Status** or **Next Deadline** directly in the table, then click **Save** to write the changes back to the spreadsheet.
- **Add case tab:** a form that appends a new row. The Case ID is suggested automatically. If you leave the email blank, the attorney's email on file is used. New rows are checked with the same validation as the morning run.
- **Needs attention tab:** rows that were skipped and why.
- **Attorney alerts tab:** **Preview attorney alerts** shows exactly what each attorney would receive. Attorneys are never emailed from the dashboard. If SMTP is configured, **Send a test copy to yourself** sends one alert to an address you type, with [TEST] in the subject.

> Close the spreadsheet in Excel before saving from the dashboard. On Windows, Excel locks the file, and the dashboard will tell you if that's the problem.

---

## Schedule it every morning

The script finds `.env`, the spreadsheet, and the output folders relative to its own location, so it doesn't matter which directory the scheduler starts it from.

### macOS / Linux (cron)

Run `crontab -e` and add this line to run at 7:00 AM, Monday to Friday:

```cron
0 7 * * 1-5 "/full/path/to/Case Tracking/.venv/bin/python" "/full/path/to/Case Tracking/run_daily.py" --no-dry-run >> "/full/path/to/Case Tracking/logs/cron.log" 2>&1
```

On macOS, cron can't read folders like Documents or Desktop by default. Either keep the project somewhere else (for example `~/case-tracker`), or give `/usr/sbin/cron` **Full Disk Access** in System Settings → Privacy & Security. The Mac must also be awake at 7:00.

### Windows (Task Scheduler)

From a Command Prompt:

```bat
schtasks /Create /TN "Case Deadline Tracker" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 07:00 ^
  /TR "\"C:\path\to\Case Tracking\.venv\Scripts\python.exe\" \"C:\path\to\Case Tracking\run_daily.py\" --no-dry-run"
```

Or use the Task Scheduler app: *Create Basic Task* → Daily at 7:00 → *Start a program*. Set **Program** to `C:\path\to\Case Tracking\.venv\Scripts\python.exe` and **Arguments** to `run_daily.py --no-dry-run`. Set **Start in** to `C:\path\to\Case Tracking`.

Leave `--no-dry-run` off until you've checked a few days of dry-run output.

---

## Replacing the spreadsheet with a case management system

All data access lives in `tracker/data_source.py`. Everything else (urgency rules, report, emails, dashboard) only calls:

- `load_cases()`: returns the valid cases, sorted most urgent first, plus the "needs attention" rows.
- `get_source()`: returns the object that does the actual reading and writing.

A source is any class with three methods:

```python
class CaseSource:
    name: str                                         # shown in the report/dashboard
    def read_rows(self) -> list[tuple[int, dict]]: ...    # (row/record number, {column: value})
    def add_case(self, record: dict) -> None: ...
    def update_case(self, case_id: str, changes: dict) -> None: ...
```

To switch to a system such as Clio, MyCase, Docketwise, or INSZoom:

1. Write a class like `ClioSource` with those three methods. It calls the system's API and maps its fields to the column names in `COLUMNS` (`"Case ID"`, `"Next Deadline"`, …).
2. Change `get_source()` to return it, for example based on a `CASE_SOURCE=clio` setting in `.env`.

Validation, urgency, sorting, the report, the emails, and the dashboard keep working unchanged. If the new system is read-only, `add_case` and `update_case` can raise an error, and the dashboard will show that error instead of saving.

---

## Tests

```bash
python -m unittest -v       # or: pytest
```

The tests cover urgency boundaries (−1, 0, 2, 3, 7, 8, 30, 31 days), sorting, validation (missing or invalid date, missing attorney, bad email, duplicate ID), an `.xlsx` add-and-edit round trip, and alert emails that include only urgent cases.

## Project layout

```
run_daily.py          morning script (report + attorney emails)
app.py                Streamlit dashboard
make_sample_data.py   creates fake demo data
tracker/
  data_source.py      spreadsheet reading/writing + validation + load_cases()   <- swap point
  urgency.py          urgency rules and sorting
  models.py           Case / Issue / Urgency types and colors
  report.py           HTML daily report
  alerts.py           per-attorney emails: build, dry-run, SMTP send
  intro.py            email intro paragraph (Claude or template)
  settings.py         .env loading, paths, logging
tests/                unit tests
```
