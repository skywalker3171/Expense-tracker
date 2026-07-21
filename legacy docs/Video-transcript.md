# Video Transcript - AI-Powered Expense Tracker (3-minute demo)

Target length: ~3 minutes. Keep narration tight; let the screens do the work.
"Screen:" lines tell you exactly what to show at each moment.

---

## 0:00 - 0:20 | Hook and problem

**Screen: App - Login/Register page.**

> "Expenses are a pain. Receipts pile up as photos, PDFs, and bank statements,
> and turning them into a clean, categorized record means hours of manual typing.
> Our Expense Tracker fixes that using an all-IBM stack: watsonx.ai for reading
> and categorizing, IBM Cloudant for data, and IBM Cloud Object Storage for the
> raw files."

---

## 0:20 - 0:40 | Register / log in

**Screen: App - register a new account (email + password), then land on the
Dashboard (empty state: "No expenses yet").**

> "I register an account. Auth is JWT-based, so from here on I only ever see my
> own data. The dashboard starts empty."

---

## 0:40 - 1:20 | Upload receipts (the core AI moment)

**Screen: App - Upload page. Drag in a receipt IMAGE first.**

> "I drop in a photo of a receipt. Behind the scenes watsonx.ai's Llama 3.2
> Vision model OCRs the image and extracts each line - date, merchant, amount -
> and Granite assigns a category."

**Screen: App - the extracted, categorized rows appear right after upload.**

**Screen: App - Upload page again. Now upload a bank-statement PDF (or CSV).**

> "Now a bank-statement PDF. A column-aware parser reads the ruled table, and
> Granite normalizes and categorizes every line - separating withdrawals from
> deposits automatically."

---

## 1:20 - 1:55 | Dashboard

**Screen: App - Dashboard. Point to the pie chart, the "Total spent" / "Total
received" cards, and the separate Expenses and Deposits tables.**

> "Everything lands on the dashboard: a category pie chart, totals for spent and
> received, and separate expense and deposit tables. Notice deposits are
> obfuscated - income figures are hidden for privacy."

---

## 1:55 - 2:20 | Natural-language query

**Screen: App - Dashboard search box. Type: "groceries from July 1st to 15th"
and hit Search; show the filtered results and updated pie.**

> "I can search in plain English. This goes to Granite, which returns a
> structured date-and-category filter, and the dashboard scopes to just those
> expenses."

---

## 2:20 - 2:40 | Learning re-categorization

**Screen: App - click the edit (pencil) on one expense's category, pick a new
category; show the "category learned" message.**

> "If a category is wrong, I fix it once. The app saves that as a rule for the
> merchant, back-applies it to existing rows, and uses it automatically on future
> uploads - so it learns my preferences."

---

## 2:40 - 3:00 | IBM Cloud proof + close

**Screen: IBM Cloud console - watsonx.ai project (expense-agent) showing the
deployed Granite and Llama models.**

**Screen: IBM Cloud console - Cloudant instance (expense-cloudant) showing the
expenses database, and the Cloud Object Storage bucket (expense-receipts-raw-jb)
with the raw uploaded files namespaced per user.**

> "It's all IBM under the hood - watsonx.ai models, Cloudant for the data, and
> Cloud Object Storage for the raw receipts. It's packaged as a single container
> ready for IBM Code Engine. Snap a receipt, and watsonx turns it into an
> organized, searchable, self-learning view of your money."

---

## Screens to prepare (checklist)

App screens:
- Login / Register page
- Dashboard (empty state, then populated: pie chart, cards, expenses + deposits)
- Upload page (drag-and-drop) with an image receipt and a bank-statement PDF/CSV
- Dashboard search box (natural-language query)
- Inline category edit (pencil) + "category learned" message

IBM Cloud console screens:
- watsonx.ai project (expense-agent) with Granite + Llama model deployments
- Cloudant instance (expense-cloudant) -> expenses database + a sample document
- Cloud Object Storage bucket (expense-receipts-raw-jb) with per-user raw files

Tip: pre-load one image receipt and one bank-statement PDF/CSV before recording
so uploads return quickly, and have a second registered account ready if you want
to show multi-tenant isolation as a bonus.


