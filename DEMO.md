# Demo script (about 5 minutes)

**Before the meeting:** double-click **`Start Demo.command`** once and press **Send test** (step 5) to make sure the email arrives. Then close the window.

**To start the demo:** double-click **`Start Demo.command`** in Finder. It does everything:

1. Creates fresh fake cases in `demo/` (your real `cases.xlsx` is never touched).
2. Runs the morning job as a dry run and opens the **daily report** in your browser.
3. Starts the **dashboard** and opens it at http://localhost:8501.

To stop, close the Terminal window.

---

## What to show and say

**1. The problem (30 sec)**
> "We track deadlines in a spreadsheet. Nobody gets warned when one is close, and a missing date can go unnoticed. One missed RFE or hearing date is a serious problem for a client."

**2. The daily report** (the first browser tab that opens) **(1 min)**
> "Every morning the tracker checks every case against today's date and builds this report. Red is overdue, orange is due in the next 2 days, yellow is this week."

Point at the **counts** at the top, then scroll to **Needs attention** at the bottom:
> "These rows have a missing date, a date written as 'TBD', or no attorney assigned. Instead of being skipped silently, they're flagged so someone fixes them."

**3. The dashboard** (second tab) **(2 min)**
- Use the sidebar filter: pick one **attorney**: "Each attorney can see just their cases."
- Search a client name, for example *Morales*.
- **Edit live:** change a case's **Current Status**, or move a **Next Deadline**, then click **Save**. The row's color and position update straight away, and the change is saved to the spreadsheet.
- **Add case** tab: add a new client with a deadline 2 days out. Back on **Cases**, it now appears in orange as CRITICAL.

**4. The attorney emails (1 min)**
- **Attorney alerts** tab → **Preview attorney alerts**. Open one attorney.
> "Each attorney gets one email every morning listing only their urgent cases. Cases that aren't urgent don't clutter their inbox."

**5. The real email (30 sec)**
- Scroll down to **Send a test copy to yourself** and enter your address, or someone's in the room. Click **Send test**.
> "That just went through our email server. When this is switched on, each attorney gets an email like this at 7 AM."

**6. Close (30 sec)**
> "No new software to learn: we keep using the spreadsheet. It runs by itself each morning, and later it can connect directly to our case management system instead of the spreadsheet."

---

## Likely questions

- **"Does it send emails without anyone checking?"** Only when it's scheduled and switched to live mode. By default it saves the emails to files instead of sending them.
- **"Is client data sent anywhere?"** No. Everything runs on this computer. Emails go only through our own email server.
- **"What if the spreadsheet has mistakes?"** Bad rows are listed under *Needs attention*, both in the report and in the dashboard.
- **"Can it use our case management system?"** Yes. Only one part of the code reads the data, and it's built to be swapped (see the README).
