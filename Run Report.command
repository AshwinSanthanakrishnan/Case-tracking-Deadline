#!/bin/bash
# Double-click in Finder: check every deadline in cases.xlsx and email the results.
# Emails go to REDIRECT_ALL_EMAILS_TO in .env if it is set, otherwise to each attorney in the spreadsheet.

cd "$(dirname "$0")" || exit 1

echo "Checking case deadlines and emailing the results..."
echo
if .venv/bin/python run_daily.py --no-dry-run; then
  echo
  echo "Done. Check your email (and the spam folder the first time)."
else
  echo
  echo "Something went wrong. See the messages above."
fi
echo
read -r -p "Press Enter to close this window." _
