import os
os.environ.pop("MCP_MODE", None)
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "Infra", "secrets.env"))
import store, chart, gmail_client
exps = store.query_expenses()
png, html = chart.build_chart_email(exps)
gmail_client.send_reply(to="skywalker3171@gmail.com", subject="Re: Chart (full test)", html_body=html, attachments=[dict(filename="expense-chart.png", mime_type="image/png", data=png)])
print("FULL_CHART_SEND_DONE", len(exps))
