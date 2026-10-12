"""Daily summary report as a self-contained HTML file."""

from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path

from . import settings
from .models import LoadResult, Urgency
from .urgency import describe_days

CSS = """
body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; color: #1f2937;
       background: #f8fafc; margin: 0; padding: 24px; }
main { max-width: 1100px; margin: 0 auto; }
h1 { margin: 0 0 4px; font-size: 24px; }
.sub { color: #64748b; margin: 0 0 24px; }
.counts { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 28px; }
.count { background: #fff; border-radius: 8px; padding: 14px 16px; border-left: 6px solid; box-shadow: 0 1px 2px rgba(0,0,0,.06); }
.count .n { font-size: 28px; font-weight: 700; }
.count .l { font-size: 13px; color: #475569; }
section { margin-bottom: 28px; }
h2 { font-size: 17px; margin: 0 0 8px; padding: 8px 12px; border-radius: 6px; }
h2 small { font-weight: 400; opacity: .8; }
table { width: 100%; border-collapse: collapse; background: #fff; font-size: 14px; box-shadow: 0 1px 2px rgba(0,0,0,.06); }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
th { background: #f1f5f9; font-size: 12px; text-transform: uppercase; letter-spacing: .03em; color: #475569; }
.tw { overflow-x: auto; }
td:first-child { white-space: nowrap; }
.empty { color: #94a3b8; font-style: italic; padding: 4px 12px; }
.issues h2 { background: #f1f5f9; color: #334155; }
footer { color: #94a3b8; font-size: 12px; margin-top: 32px; }
"""


def render_report(result: LoadResult, today: date, firm_name: str = settings.FIRM_NAME) -> str:
    by_level = {level: [c for c in result.cases if c.urgency is level] for level in Urgency}

    counts = "".join(
        f'<div class="count" style="border-color:{lvl.color}"><div class="n" style="color:{lvl.color}">'
        f'{len(by_level[lvl])}</div><div class="l">{lvl.value}<br>{escape(lvl.description)}</div></div>'
        for lvl in Urgency
    )
    counts += (
        f'<div class="count" style="border-color:#64748b"><div class="n">{len(result.issues)}</div>'
        f'<div class="l">NEEDS ATTENTION<br>Rows with bad data</div></div>'
    )

    sections = []
    for level in Urgency:
        cases = by_level[level]
        heading = (
            f'<h2 style="background:{level.background};color:{level.color}">{level.icon} {level.value} '
            f'<small>— {escape(level.description)} · {len(cases)} case{"s" if len(cases) != 1 else ""}</small></h2>'
        )
        if not cases:
            sections.append(f'<section>{heading}<p class="empty">None</p></section>')
            continue
        rows = "".join(
            "<tr>"
            f"<td>{escape(c.case_id)}</td><td>{escape(c.client_name)}</td><td>{escape(c.case_type)}</td>"
            f"<td>{escape(c.deadline_type)}</td><td>{c.deadline:%b %d, %Y}</td>"
            f'<td style="color:{level.color};font-weight:600">{describe_days(c.days_left)}</td>'
            f"<td>{escape(c.status)}</td><td>{escape(c.attorney)}</td>"
            "</tr>"
            for c in cases
        )
        sections.append(
            f"<section>{heading}<div class=\"tw\"><table><tr><th>Case ID</th><th>Client</th><th>Case type</th><th>Deadline type</th>"
            f"<th>Deadline</th><th>When</th><th>Status</th><th>Attorney</th></tr>{rows}</table></div></section>"
        )

    if result.issues:
        issue_rows = "".join(
            f"<tr><td>{i.row_number}</td><td>{escape(i.case_id) or '—'}</td><td>{escape(i.client_name) or '—'}</td>"
            f"<td>{escape('; '.join(i.problems))}</td></tr>"
            for i in result.issues
        )
        issues_html = (
            f"<div class=\"tw\"><table><tr><th>Row</th><th>Case ID</th><th>Client</th><th>Problem</th></tr>{issue_rows}</table></div>"
        )
    else:
        issues_html = '<p class="empty">All rows are valid.</p>'

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Deadline Report {today:%Y-%m-%d}</title><style>{CSS}</style></head>
<body><main>
<h1>Case Deadline Report</h1>
<p class="sub">{escape(firm_name)} · {today:%A, %B %d, %Y} · {len(result.cases)} active cases from {escape(result.source_name)}</p>
<div class="counts">{counts}</div>
{''.join(sections)}
<section class="issues"><h2>⚠️ Needs attention <small>— {len(result.issues)} row(s) skipped</small></h2>{issues_html}</section>
<footer>Generated {today:%Y-%m-%d} by the case deadline tracker. Confidential — attorney work product.</footer>
</main></body></html>"""


def write_report(result: LoadResult, today: date, out_dir: Path | None = None) -> Path:
    out_dir = (out_dir or settings.OUTPUT_DIR) / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"deadline_report_{today:%Y-%m-%d}.html"
    path.write_text(render_report(result, today), encoding="utf-8")
    return path
