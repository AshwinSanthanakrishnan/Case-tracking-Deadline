#!/bin/bash
# One-click demo of the Case Deadline Tracker. Double-click this file in Finder.
#
# Uses its own FAKE data in demo/ — your real cases.xlsx, report folder and log are never touched,
# and no attorney is emailed: alerts go only to REDIRECT_ALL_EMAILS_TO (if set), otherwise nothing is sent.

cd "$(dirname "$0")" || exit 1

export CASES_FILE="demo/cases_demo.xlsx"
export OUTPUT_DIR="demo/output"
export LOG_FILE="demo/demo.log"
PY=".venv/bin/python"

pause_and_exit() { echo; read -r -p "Press Enter to close this window." _; exit 1; }

if [ ! -x "$PY" ]; then
  echo "First-time setup: installing Python packages (about a minute)..."
  python3 -m venv .venv && "$PY" -m pip install -q -r requirements.txt || { echo "Setup failed."; pause_and_exit; }
fi

echo
echo "Step 1 of 3  Creating fresh demo cases (deadlines relative to today)..."
"$PY" make_sample_data.py --out "$CASES_FILE" || pause_and_exit

echo
# Emails are only really sent when REDIRECT_ALL_EMAILS_TO is set in .env, so they all go to you,
# never to the (fake) demo attorneys. Otherwise this is a dry run and emails are saved to demo/output/.
SEND_TO="$("$PY" -c 'from tracker import settings; print(settings.REDIRECT_TO)')"
if [ -n "$SEND_TO" ]; then
  echo "Step 2 of 3  Running the morning job and emailing all alerts to $SEND_TO..."
  "$PY" run_daily.py --no-dry-run || pause_and_exit
else
  echo "Step 2 of 3  Running the morning job (dry run: emails are saved, not sent)..."
  echo "             Tip: set REDIRECT_ALL_EMAILS_TO in .env to receive the alert emails yourself."
  "$PY" run_daily.py --dry-run || pause_and_exit
fi
open "demo/output/reports/deadline_report_$(date +%F).html"

echo
echo "Step 3 of 3  Starting the dashboard..."
pkill -f "streamlit run app.py" 2>/dev/null   # stop any earlier copy so port 8501 is free
"$PY" -m streamlit run app.py --server.port 8501 --server.headless true >demo/dashboard.log 2>&1 &
DASHBOARD_PID=$!
trap 'kill $DASHBOARD_PID 2>/dev/null' EXIT

for _ in $(seq 1 30); do
  curl -s -o /dev/null http://localhost:8501 && break
  sleep 1
done
if ! curl -s -o /dev/null http://localhost:8501; then
  echo "The dashboard didn't start. Details are in demo/dashboard.log."
  pause_and_exit
fi
open http://localhost:8501

echo
echo "================================================================"
echo "  Demo is running:  http://localhost:8501"
echo "  Report and sample emails:  demo/output/"
echo "  To stop: close this window (or press Ctrl+C)."
echo "================================================================"
wait $DASHBOARD_PID
