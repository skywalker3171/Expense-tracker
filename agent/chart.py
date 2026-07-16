"""
chart.py — build a monthly expense summary:
  - pie chart PNG (matplotlib, Agg backend)
  - HTML table of individual expenses
"""
from __future__ import annotations

import io
import logging
from collections import defaultdict
from datetime import datetime

log = logging.getLogger(__name__)

# Use non-interactive backend — no display needed
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# ---------------------------------------------------------------------------
# Pie chart
# ---------------------------------------------------------------------------

# Consistent colour palette (one per category, 10 total)
_CATEGORY_COLORS = {
    "Groceries":     "#4e79a7",
    "Dining":        "#f28e2b",
    "Transport":     "#e15759",
    "Utilities":     "#76b7b2",
    "Housing":       "#59a14f",
    "Health":        "#edc948",
    "Entertainment": "#b07aa1",
    "Shopping":      "#ff9da7",
    "Travel":        "#9c755f",
    "Other":         "#bab0ac",
}


def build_pie_chart(expenses: list[dict]) -> bytes:
    """
    Aggregate expenses by category and return a PNG pie chart as bytes.
    """
    totals: dict[str, float] = defaultdict(float)
    for exp in expenses:
        totals[exp.get("category", "Other")] += exp.get("amount", 0.0)

    if not totals:
        log.warning("No expenses to chart")
        # Return a blank 1x1 PNG
        fig, ax = plt.subplots(figsize=(1, 1))
        ax.axis("off")
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        return buf.getvalue()

    labels = list(totals.keys())
    sizes  = [totals[l] for l in labels]
    colors = [_CATEGORY_COLORS.get(l, "#bab0ac") for l in labels]

    fig, ax = plt.subplots(figsize=(7, 7))
    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=labels,
        colors=colors,
        autopct="%1.1f%%",
        startangle=140,
        pctdistance=0.82,
    )
    for t in texts:
        t.set_fontsize(11)
    for at in autotexts:
        at.set_fontsize(9)

    total = sum(sizes)
    ax.set_title(f"Expense Summary  •  Total: ${total:,.2f} CAD", fontsize=13, pad=16)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# HTML table
# ---------------------------------------------------------------------------

def build_html_table(expenses: list[dict]) -> str:
    """
    Return a self-contained HTML snippet with an expense table,
    sorted by date descending.
    """
    sorted_expenses = sorted(expenses, key=lambda e: e.get("date", ""), reverse=True)

    rows_html = ""
    for exp in sorted_expenses:
        rows_html += (
            f"<tr>"
            f"<td>{exp.get('date','')}</td>"
            f"<td>{exp.get('merchant','')}</td>"
            f"<td style='text-align:right'>${exp.get('amount',0):.2f}</td>"
            f"<td>{exp.get('currency','CAD')}</td>"
            f"<td>{exp.get('category','Other')}</td>"
            f"</tr>\n"
        )

    total = sum(e.get("amount", 0) for e in expenses)

    return f"""
<html><body style="font-family:Arial,sans-serif;font-size:13px;">
<h2>Expense Report</h2>
<p>Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} &nbsp;|&nbsp; {len(expenses)} items</p>
<table border="1" cellpadding="6" cellspacing="0"
       style="border-collapse:collapse;width:100%;max-width:700px;">
  <thead style="background:#3b82d4;color:white;">
    <tr>
      <th>Date</th><th>Merchant</th><th>Amount</th><th>Currency</th><th>Category</th>
    </tr>
  </thead>
  <tbody>
{rows_html}  </tbody>
  <tfoot>
    <tr style="font-weight:bold;background:#f7f8fa;">
      <td colspan="2">Total</td>
      <td style="text-align:right">${total:.2f}</td>
      <td>CAD</td>
      <td></td>
    </tr>
  </tfoot>
</table>
<p style="color:#888;font-size:11px;">Powered by IBM watsonx.ai + Cloudant</p>
</body></html>
"""


# ---------------------------------------------------------------------------
# Combined email body builder
# ---------------------------------------------------------------------------

def build_chart_email(expenses: list[dict]) -> tuple[bytes, str]:
    """
    Returns (png_bytes, html_body) ready for gmail_client.send_reply().
    """
    png  = build_pie_chart(expenses)
    html = build_html_table(expenses)
    # Embed the chart inline as a data URI in the HTML
    import base64
    b64 = base64.b64encode(png).decode()
    html_with_chart = html.replace(
        "<h2>Expense Report</h2>",
        f'<h2>Expense Report</h2>\n<img src="data:image/png;base64,{b64}" '
        f'alt="Expense pie chart" style="max-width:500px;"/><br/>',
    )
    return png, html_with_chart
