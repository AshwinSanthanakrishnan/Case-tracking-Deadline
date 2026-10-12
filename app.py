"""Interactive dashboard:  streamlit run app.py

A thin UI over the same tracker package the morning script uses — loading,
validation, urgency rules, report and alert emails all come from tracker/.
"""

from __future__ import annotations

from datetime import date, timedelta

import os

import pandas as pd
import streamlit as st

from tracker import settings
from tracker.alerts import build_alerts, send_test
from tracker.data_source import get_source, load_cases, parse_date, suggest_case_id, validate_row
from tracker.intro import ai_enabled
from tracker.models import Case, Issue, Urgency
from tracker.report import render_report
from tracker.urgency import describe_days

CASE_TYPES = ["N-400", "I-130", "I-485", "Asylum", "RFE Response"]
DEADLINE_TYPES = ["Filing deadline", "RFE response due", "Biometrics appointment", "Court hearing"]
EDITABLE = ["Current Status", "Next Deadline"]

st.set_page_config(page_title="Case Deadline Tracker", page_icon="⚖️", layout="wide")
log = settings.setup_logging()
state = st.session_state
state.setdefault("version", 0)  # Bumped after each save so widgets reset cleanly.
state.setdefault("flash", [])


def flash_and_rerun(message: str) -> None:
    state.flash.append(message)
    state.version += 1
    state.pop("alerts", None)  # Data changed, so any previewed emails are stale.
    st.rerun()


# --------------------------------------------------------------------------- #
# Load (every rerun, so edits made here or in Excel show up immediately)
# --------------------------------------------------------------------------- #
today = date.today()
source = get_source()
try:
    result = load_cases(source, today=today)
except (FileNotFoundError, ValueError) as exc:
    st.error(f"Could not load cases: {exc}")
    st.info("Create demo data with `python make_sample_data.py`, or set CASES_FILE in .env.")
    st.stop()

cases = result.cases
attorneys = sorted({c.attorney for c in cases})
known_emails = {c.attorney: c.attorney_email for c in cases}

# --------------------------------------------------------------------------- #
# Sidebar: filters
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("Filters")
    levels = st.multiselect("Urgency", [u.value for u in Urgency], default=[u.value for u in Urgency])
    chosen_attorneys = st.multiselect("Assigned attorney", attorneys, placeholder="All attorneys")
    search = st.text_input("Search client name", placeholder="e.g. Morales").strip().lower()
    st.divider()
    st.caption(f"Data source: **{result.source_name}**  \nToday: **{today:%a %b %d, %Y}**")
    if st.button("Reload from spreadsheet", width="stretch"):
        st.rerun()
    st.download_button(
        "Download today's HTML report",
        render_report(result, today),
        file_name=f"deadline_report_{today:%Y-%m-%d}.html",
        mime="text/html",
        width="stretch",
    )

# --------------------------------------------------------------------------- #
# Header + counts
# --------------------------------------------------------------------------- #
st.title("⚖️ Case Deadline Tracker")
for message in state.flash:
    st.success(message)
state.flash = []


def count(*levels_: Urgency) -> int:
    return sum(1 for c in cases if c.urgency in levels_)


m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("🔴 Overdue", count(Urgency.OVERDUE), help="Deadline has passed")
m2.metric("🟠 Critical", count(Urgency.CRITICAL), help="Due in 0–2 days")
m3.metric("🟡 This week", count(Urgency.CRITICAL, Urgency.WARNING), help="Due in 0–7 days (critical + warning)")
m4.metric("Total cases", len(cases), help="Valid cases being tracked")
m5.metric("⚠️ Needs attention", len(result.issues), help="Rows skipped because of missing or invalid data")

tab_cases, tab_add, tab_issues, tab_alerts = st.tabs(
    ["📋 Cases", "➕ Add case", f"⚠️ Needs attention ({len(result.issues)})", "✉️ Attorney alerts"]
)

# --------------------------------------------------------------------------- #
# Cases table (editable status + deadline)
# --------------------------------------------------------------------------- #
with tab_cases:
    shown = [
        c for c in cases
        if c.urgency.value in levels
        and (not chosen_attorneys or c.attorney in chosen_attorneys)
        and (not search or search in c.client_name.lower())
    ]
    st.caption(f"Showing {len(shown)} of {len(cases)} cases, most urgent first. "
               "Edit **Current Status** or **Next Deadline** in the table, then click Save.")

    def to_row(c: Case) -> dict:
        return {
            "Urgency": f"{c.urgency.icon} {c.urgency.value}",
            "Case ID": c.case_id,
            "Client Name": c.client_name,
            "Case Type": c.case_type,
            "Current Status": c.status,
            "Next Deadline": c.deadline,
            "When": describe_days(c.days_left),
            "Deadline Type": c.deadline_type,
            "Assigned Attorney": c.attorney,
        }

    by_id = {c.case_id: c for c in shown}

    def color_row(row: pd.Series) -> list[str]:
        # Streamlit only applies Styler colors to read-only columns, so editable cells stay plain.
        level = by_id[row["Case ID"]].urgency
        return [
            "" if col in EDITABLE
            else f"background-color: {level.background}; color: {level.color if col == 'Urgency' else '#1f2937'}"
            for col in row.index
        ]

    if shown:
        original = pd.DataFrame([to_row(c) for c in shown])
        # Keyed on the visible rows so pending edits never land on the wrong case after filtering.
        editor_key = f"editor_{state.version}_{hash(tuple(original['Case ID']))}"
        edited = st.data_editor(
            original.style.apply(color_row, axis=1).set_properties(subset=["Urgency"], **{"font-weight": "bold"}),
            key=editor_key,
            hide_index=True,
            width="stretch",
            height=min(38 + 35 * len(shown), 700),  # Show every row without inner scrolling.
            num_rows="fixed",
            disabled=[c for c in original.columns if c not in EDITABLE],
            column_config={
                "Urgency": st.column_config.TextColumn(width=125),
                "Current Status": st.column_config.TextColumn(required=True, width="medium"),
                "Next Deadline": st.column_config.DateColumn(required=True, format="YYYY-MM-DD"),
            },
        )

        changes: dict[str, dict] = {}
        for (_, before), (_, after) in zip(original.iterrows(), edited.iterrows()):
            diff = {}
            if str(after["Current Status"]).strip() != before["Current Status"]:
                diff["Current Status"] = str(after["Current Status"]).strip()
            new_deadline = parse_date(after["Next Deadline"])
            if new_deadline != before["Next Deadline"]:
                diff["Next Deadline"] = new_deadline
            if diff:
                changes[before["Case ID"]] = diff

        col_save, col_note = st.columns([1, 4])
        if col_save.button(f"Save {len(changes)} change(s)", type="primary", disabled=not changes):
            bad = [cid for cid, d in changes.items() if ("Next Deadline" in d and d["Next Deadline"] is None)
                   or ("Current Status" in d and not d["Current Status"])]
            if bad:
                st.error(f"Status and deadline can't be blank (check {', '.join(bad)}).")
            else:
                try:
                    for case_id, diff in changes.items():
                        source.update_case(case_id, diff)
                        log.info("Dashboard edit: %s %s", case_id,
                                 ", ".join(f"{k} -> {v}" for k, v in diff.items()))
                except PermissionError:
                    st.error(f"Couldn't write to {result.source_name}. Is it open in Excel? Close it and try again.")
                except KeyError as exc:
                    st.error(str(exc))
                else:
                    flash_and_rerun(f"Saved {len(changes)} change(s) to {result.source_name}.")
        if changes:
            col_note.caption("Unsaved: " + ", ".join(changes))
    else:
        st.info("No cases match the current filters.")

# --------------------------------------------------------------------------- #
# Add a case
# --------------------------------------------------------------------------- #
with tab_add:
    all_ids = [c.case_id for c in cases] + [i.case_id for i in result.issues if i.case_id]
    with st.form(f"add_case_{state.version}"):
        c1, c2 = st.columns(2)
        case_id = c1.text_input("Case ID", value=suggest_case_id(all_ids))
        client = c2.text_input("Client name")
        case_type = c1.selectbox("Case type", CASE_TYPES, index=None, accept_new_options=True,
                                 placeholder="Choose or type…")
        status = c2.text_input("Current status", placeholder="e.g. Awaiting client documents")
        deadline = c1.date_input("Next deadline", value=today + timedelta(days=30), format="YYYY-MM-DD")
        deadline_type = c2.selectbox("Deadline type", DEADLINE_TYPES, index=None, accept_new_options=True,
                                     placeholder="Choose or type…")
        attorney = c1.selectbox("Assigned attorney", attorneys, index=None, accept_new_options=True,
                                placeholder="Choose or type a new name…")
        email = c2.text_input("Attorney email", placeholder="Leave blank to use the attorney's email on file")
        submitted = st.form_submit_button("Add case", type="primary")

    if submitted:
        record = {
            "Case ID": case_id.strip(),
            "Client Name": client.strip(),
            "Case Type": case_type or "",
            "Current Status": status.strip(),
            "Next Deadline": deadline,
            "Deadline Type": deadline_type or "",
            "Assigned Attorney": attorney or "",
            "Attorney Email": email.strip() or known_emails.get(attorney or "", ""),
        }
        # Same validation the morning run applies, so nothing added here ends up in "Needs attention".
        checked = validate_row(record, row_number=0)
        problems = checked.problems if isinstance(checked, Issue) else []
        if record["Case ID"] in all_ids:
            problems.append(f"Case ID {record['Case ID']} already exists")
        if problems:
            st.error("Please fix: " + "; ".join(problems))
        else:
            try:
                source.add_case(record)
            except PermissionError:
                st.error(f"Couldn't write to {result.source_name}. Is it open in Excel? Close it and try again.")
            else:
                log.info("Dashboard add: %s (%s, %s) deadline %s", record["Case ID"], record["Client Name"],
                         record["Case Type"], deadline)
                flash_and_rerun(f"Added {record['Case ID']} for {record['Client Name']}.")

# --------------------------------------------------------------------------- #
# Needs attention
# --------------------------------------------------------------------------- #
with tab_issues:
    if result.issues:
        st.caption(f"These rows are skipped by the tracker and the morning emails until fixed in "
                   f"**{result.source_name}**. Click *Reload* in the sidebar after fixing.")
        st.dataframe(
            pd.DataFrame([{
                "Row": i.row_number,
                "Case ID": i.case_id or "—",
                "Client Name": i.client_name or "—",
                "Problem": "; ".join(i.problems),
                "Next Deadline (as entered)": i.raw.get("Next Deadline", ""),
                "Assigned Attorney": i.raw.get("Assigned Attorney", ""),
            } for i in result.issues]),
            hide_index=True,
            width="stretch",
        )
    else:
        st.success("Every row in the spreadsheet is valid.")

# --------------------------------------------------------------------------- #
# Attorney alert preview (dry run — never sends)
# --------------------------------------------------------------------------- #
with tab_alerts:
    st.caption("Shows exactly what the morning run would email each attorney "
               "(OVERDUE, CRITICAL and WARNING cases only). **Nothing is sent to attorneys from here.**")
    if ai_enabled():
        use_ai = st.toggle("Have Claude write each intro paragraph", value=True)
    else:
        use_ai = False
        st.caption("Set `ANTHROPIC_API_KEY` in .env to have Claude write the intro paragraphs; "
                   "a standard template is used otherwise.")

    if st.button("Preview attorney alerts", type="primary"):
        with st.spinner("Building emails…"):
            state.alerts = build_alerts(cases, today, use_ai=use_ai)
        log.info("Dashboard: previewed %d attorney alert(s)", len(state.alerts))

    if "alerts" in state:
        if not state.alerts:
            st.success("No attorney has overdue, critical or warning cases today — no emails would be sent.")
        for alert in state.alerts:
            label = f"**{alert.attorney}** · {alert.email} · {len(alert.cases)} case(s)"
            with st.expander(label, expanded=len(state.alerts) == 1):
                st.markdown(f"**Subject:** {alert.subject}  \n"
                            f"**Intro written by:** {'Claude' if alert.intro_source == 'claude' else 'template'}")
                st.html(alert.html_body)

        smtp = settings.smtp_settings()
        if state.alerts and smtp.is_configured:
            st.divider()
            st.subheader("Send a test copy to yourself")
            st.caption("Sends one attorney's alert to the address you enter, with [TEST] in the subject, "
                       "so you can see the real email arrive. The attorney is not emailed.")
            c1, c2, c3 = st.columns([2, 3, 1], vertical_alignment="bottom")
            by_name = {a.attorney: a for a in state.alerts}
            which = c1.selectbox("Alert for", list(by_name))
            to_address = c2.text_input("Send to", value=os.getenv("DEMO_TEST_EMAIL", smtp.username))
            if c3.button("Send test", width="stretch"):
                if "@" not in to_address:
                    st.error("Enter a valid email address.")
                else:
                    try:
                        with st.spinner("Sending…"):
                            send_test(by_name[which], to_address.strip(), smtp)
                        st.success(f"Test email sent to {to_address}. Check that inbox (and spam).")
                    except (OSError, RuntimeError) as exc:  # smtplib errors are OSErrors
                        st.error(f"Couldn't send: {exc}")
