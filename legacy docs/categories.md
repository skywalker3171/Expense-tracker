# Categories & Category-Rule Learning

## 1. The category list

Every expense is mapped to exactly one category. The system ships with a fixed
default list defined in `agent/config.py`:

> **Groceries, Dining, Transport, Utilities, Housing, Health, Entertainment,
> Shopping, Travel, Other**

`Other` is the catch-all/fallback. The list is **per-user and editable**:

- `GET /api/categories` returns the caller's list (`store.get_categories(user_id)`).
- `PUT /api/categories` saves an edited list (`store.set_categories`), stored in
  Cloudant under a per-user doc id (`settings:categories:{user_id}`), de-duplicated
  and trimmed. If a user has never customized it, the code falls back to the
  `config.CATEGORIES` defaults. Because each user's list is namespaced by
  `user_id`, one user can never overwrite another user's (or a global) list.

## 2. How a category is first assigned (AI)

When a file is ingested, the model is *prompted with the active category list* and
told to map each transaction to one of them:

- **Images / scanned PDFs** → Llama-3.2-11B-Vision (`parse_image_receipt`).
- **CSV / text PDFs** → Granite-3-8B-Instruct (`categorize_text`).

The model's guess is defensive-coded: `schema.coerce_category()` accepts the value
only if it matches an allowed category (case-insensitive, with a Title-case retry);
anything unrecognized falls back to `Other`. So the model can never introduce an
off-list category.

## 3. Category-rule learning (the key feature)

The tracker **learns each user's preferred categorization over time**. A learned
rule is a simple, deterministic mapping:

    normalized_merchant  →  category   (scoped per user)

### 3a. Teaching a rule — inline re-categorization
When a user changes an expense's category from the dashboard
(`PATCH /api/expenses/{id}` → `recategorize()` in `web/backend/routes_expenses.py`):

1. The edited expense's category is validated (`coerce_category`) and saved.
2. The merchant name is turned into a stable key by `schema.normalize_merchant()`
   (lowercased; store numbers like `#123`, POS/debit/credit noise words, and long
   digit runs are stripped) — so "STARBUCKS #4821" and "Starbucks POS 900" collapse
   to the same key.
3. That `merchant_key → category` rule is persisted per user via
   `store.upsert_category_rule()` as a Cloudant doc
   (`catrule:{user_id}:{merchant_key}`, `type: "category_rule"`).
4. **Back-application:** every existing (non-deposit) expense of that user with the
   same normalized merchant is immediately updated to the new category, so the fix
   is retroactive, not just going forward.

### 3b. Applying rules — automatic on future uploads
In `agent/pipeline.py` (`process_file`), after parsing but before saving, the code
loads the user's rules (`store.get_category_rules`) and overrides the AI's guess
for any known merchant:

```python
rules = store.get_category_rules(user_id)
for doc in expenses:
    if doc.get("flow") != "deposit":
        key = schema.normalize_merchant(doc.get("merchant", ""))
        if key in rules:
            doc["category"] = rules[key]   # user's rule wins over the model
    store.upsert_expense(doc)
```

So once a user corrects a merchant even once, all future receipts from that
merchant are auto-categorized their way — the model's guess is only used when no
learned rule exists yet.

## 4. Scope, safety, and notes

- **Deposits are never categorized.** Rules and re-categorization apply only to
  spending expenses (`flow != "deposit"`); the `PATCH` endpoint rejects deposits.
- **Per-user isolation.** Both the category list and the learned rules are keyed by
  `user_id`, so learning is private to each account.
- **Deterministic, not a model.** Rule matching is a plain dictionary lookup on the
  normalized merchant key — fast, predictable, and free of extra LLM calls.
- **Reset.** `POST /api/reset` (`store.delete_user_expenses`) deletes the user's
  expenses *and* their learned `category_rule` docs, so a demo reset also clears
  what the tracker has learned.

## 5. End-to-end flow (summary)

1. Upload → AI assigns a best-guess category from the user's active list.
2. Any saved rule for that merchant overrides the AI guess automatically.
3. User corrects a category once → the choice is stored as a per-user merchant
   rule and back-applied to all matching past expenses.
4. From then on, every future upload from that merchant is auto-categorized the
   user's way — the tracker "learns" without any additional model training.
