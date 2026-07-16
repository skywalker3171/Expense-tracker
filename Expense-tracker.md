# Expense Tracker - Implementation Plan (IBM Cloud, Dallas)

## Confirmed services
- cloud-object-storage
- cloudantnosqldb
- secrets-manager
- pm-20 (Watson Machine Learning / watsonx.ai)

## MCP Servers (replacing custom integration modules)
| # | MCP Server | Replaces | Purpose |
|---|---|---|---|
| 1 | Gmail MCP | `gmail_client.py` | Poll inbox, download attachments, apply labels, send replies |
| 2 | Cloudant MCP (CouchDB-compatible) | `store.py` (Cloudant half) | Upsert and query expense documents |
| 3 | IBM COS MCP (S3-compatible) | `store.py` (COS half) | Upload raw attachments to `expense-receipts-raw-jb` bucket |

## Model stack (locked)
- meta-llama/llama-3-2-11b-vision-instruct -> OCR + field extraction from image / scanned-PDF receipts (multimodal, single call)
- ibm/granite-3-8b-instruct -> normalize + categorize CSV rows and text-PDFs into 7-10 categories; also builds the "Chart" summary

## Architecture at a glance

    Gmail MCP <--poll every 10m--> Code Engine (Python agent)
                                          |
        +---------------------------------+----------------------------+
        v                                 v                            v
    COS MCP (raw attachments)       watsonx.ai                Cloudant MCP (expenses)
                               Llama-3.2-11b-vision (OCR)
                               Granite-3-8b (categorize)
                                          |
                 "Chart" email --> Gmail MCP reply (PNG + HTML table)

## PHASE 0 - Prerequisites (status)
- T0.1 [x] Logged in, targeted us-south (Dallas)
- T0.2 [x] Plugins present: code-engine 1.62.6, secrets-manager 2.0.16
- T0.3 [x] Python 3.13.3 installed
- T0.4 [x] ibmcloud target -g Default (set resource group)
- T0.5 [x] (optional) ibmcloud on PATH (CLI resolves in shell)
- T0.6 [x] Gmail: OAuth Desktop client created; credentials.json + refresh.token generated locally
- T0.7 [x] Gmail MCP registered (@gongrzhe/server-gmail-autoauth-mcp); auth verified ("Authentication completed successfully")
- T0.8 [x] Cloudant MCP registered (couchdb-mcp-server); service key expense-cloudant-key created; CLOUDANT_URL + CLOUDANT_APIKEY set in Bob config
- T0.9 [x] IBM COS MCP registered (aws-s3-mcp, S3-compatible); service key expense-cos-key (HMAC) created; endpoint https://s3.us-south.cloud-object-storage.appdomain.cloud + HMAC keys set in Bob config

## PHASE 0 - COMPLETE. Note: restart Bob to load the 3 MCP servers; verify tools (gmail_list_messages / cloudant_upsert / s3_put_object) are callable, then proceed to PHASE 1.

## PHASE 1 - Provision infrastructure (CLI)
- T1.1 [x] COS instance: REUSING existing "CloudObjectStorage" (guid 27cc4856-b162-4904-9c5d-981f56382975)
- T1.2 [x] COS bucket created: expense-receipts-raw-jb (us-south, Standard)
- T1.3 [x] Cloudant instance created: expense-cloudant (us-south, lite, guid 8ce9c85d-65c7-4b94-ad36-c381f64ee98d)
- T1.4 [x] Secrets Manager instance created: expense-secrets (guid 98b1fcc3-a044-4007-9e1c-a43d737a53e1, trial, us-south, private-only VPE)
- T1.5 [x] WML (pm-20) instance created: expense-wml (guid 3514245f-5f1a-45a6-819a-2135c9d93781, lite, us-south)
- T1.6 [x] watsonx project created: expense-agent (project_id 3885967a-6227-4fff-9b47-f7f799237543); COS associated
- T1.7 [ ] Code Engine project: BLOCKED — ibmcloud ce requires a paid account; defer to Phase 6
      ibmcloud ce project create --name expense-agent
- T1.8 [x] IAM API key created: expense-agent-key (id ApiKey-6645937d-5e3f-402a-86f9-e1ae4d6fda12); all secrets written to secrets.env

## PHASE 2 - Canonical Expense data contract - COMPLETE
- [x] agent/schema.py: build_expense(), validate_expense(), coerce_date/amount/category helpers
- Every parser emits this JSON shape (stored one doc per expense in Cloudant):
      {
        "id": "sha256(source_email_id + line_index)",
        "date": "YYYY-MM-DD",
        "merchant": "string",
        "amount": 0.00,
        "currency": "CAD",
        "category": "one of the 7-10 categories",
        "source_type": "pdf | image | csv",
        "source_email_id": "gmail message id",
        "raw_text": "extracted text",
        "created_at": "ISO-8601"
      }
- Categories (fixed list): Groceries, Dining, Transport, Utilities, Housing, Health, Entertainment, Shopping, Travel, Other
- [x] agent/config.py: all secrets loaded from env vars; secrets.env written with all 12 keys

## PHASE 3 - Python agent - COMPLETE
- Repo layout (all files created, syntax-verified):
      agent/
        main.py            # [x] run_once() poll loop + --loop mode
        gmail_client.py    # [x] Gmail MCP wrapper: list/get/download/mark_processed/send_reply
        router.py          # [x] dispatch by MIME/extension: csv | text-pdf | image | scanned-pdf
        parsers.py         # [x] csv (pandas) + text-pdf (pdfplumber) -> Granite
        watsonx_client.py  # [x] vision OCR (Llama) + text categorize (Granite)
        store.py           # [x] Cloudant MCP upsert/query + COS MCP upload
        chart.py           # [x] pie chart PNG + HTML table + build_chart_email()
        config.py          # [x] load secrets from env
        schema.py          # [x] canonical expense contract
        requirements.txt   # [x] all deps (ibm-watsonx-ai, pandas, pdfplumber, matplotlib, etc.)
- T3.1 [x] gmail_client: gmail_list_messages (subject:Expense OR subject:Chart, is:unread); gmail_get_attachment
- T3.2 [x] idempotency: gmail_modify_message applies label "Processed" + removes UNREAD after handling
- T3.3 [x] router: routes by MIME/extension → csv / text-pdf / image / scanned-pdf (pdf2image)
- T3.4 [x] store (Cloudant half): cloudant_upsert to save each expense; cloudant_query for chart aggregation
- T3.5 [x] store (COS half): s3_put_object uploads raw attachments to expense-receipts-raw-jb

## PHASE 4 - Model integration (watsonx.ai) - COMPLETE
- T4.1 [x] watsonx_client: IAM apikey -> bearer token (cached); calls ml/v1/text/chat
- T4.2 [x] Image/scanned-PDF: base64 image → llama-3-2-11b-vision-instruct; JSON array response
- T4.3 [x] CSV/text-PDF: extracted text → ibm/granite-3-8b-instruct; normalized rows + category
- T4.4 [x] Schema enforced: validate_expense(), coerce_amount/date, category defaults to Other

## PHASE 5 - Chart handler ("Chart" email) - COMPLETE
- T5.1 [x] subject:Chart triggers query_expenses() via Cloudant MCP cloudant_query
- T5.2 [x] chart.py aggregates totals by category (defaultdict)
- T5.3 [x] chart.py renders pie chart PNG with matplotlib (Agg backend, 150dpi, 10-colour palette)
- T5.4 [x] chart.py builds HTML table (date, merchant, amount, currency, category + total row)
- T5.5 [x] build_chart_email() embeds PNG inline as base64 data URI; gmail_client.send_reply() dispatches

## PHASE 6 - Deploy to Code Engine (10-min scheduler)
- T6.1 [ ] Store all secrets as a Code Engine secret:
      ibmcloud ce secret create --name expense-secrets --from-env-file .env
- T6.2 [ ] Build + deploy the app from source:
      ibmcloud ce app create --name expense-agent --build-source . --env-from-secret expense-secrets
- T6.3 [ ] Create a periodic cron subscription (every 10 min) that pings the app:
      ibmcloud ce sub cron create --name poll-10m --destination expense-agent --schedule "*/10 * * * *"
- T6.4 [ ] Alternative: deploy as a CE Job + Ping event source instead of an always-on app (cheaper)

## PHASE 7 - Test and acceptance
- T7.1 [ ] Send test email subject:Expense with a CSV -> rows appear in Cloudant
- T7.2 [ ] Send subject:Expense with an image receipt -> vision OCR extracts + categorizes
- T7.3 [ ] Re-send same email -> no duplicates (idempotency holds)
- T7.4 [ ] Send subject:Chart -> receive reply with pie chart PNG + HTML table
- T7.5 [ ] Confirm 10-min cron fires and processes new mail automatically
