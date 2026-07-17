import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "secrets.env"))
import store, chart
exps = store.query_expenses()
print("Expenses found:", len(exps))
png, html = chart.build_chart_email(exps)
open(os.path.join(os.path.dirname(__file__), "expense-chart.png"), "wb").write(png)
open(os.path.join(os.path.dirname(__file__), "expense-report.html"), "w", encoding="utf-8").write(html)
print("Wrote expense-chart.png and expense-report.html")
