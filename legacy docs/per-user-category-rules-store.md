# Per-User "Category Rules" Store — Re-categorization with Learning

## Goal

Let a user manually change an expense's category, and have the AI **remember that
choice** so the next time an identical or similar expense is uploaded it is
categorized the same way — automatically, instantly, and per-user.

This is achieved with a lightweight **feedback / override layer** stored in
Cloudant, not by retraining or fine-tuning the model. It is cheaper, predictable,
and takes effect immediately.

## Core idea

When the user corrects an expense's category, do **two** things:

1. **Update that one expense** in Cloudant (the immediate fix).
2. **Save a "category rule"** that maps *expenses like this one* → the chosen
   category. On every future upload, apply matching rules **after** the AI returns
   its guess, overriding the AI when a rule matches.

The primary match signal is the **normalized merchant** (already extracted for
every expense). Rules are scoped by `user_id`, so each user teaches their own tracker.

## Data model — new Cloudant doc type (reuse the existing DB)

A new document type alongside the existing `expense` / `settings` docs, scoped by
`user_id`:

```json
{
  "_id": "catrule:<user_id>:<merchant_key>",
  "type": "category_rule",
  "user_id": "user-123",
  "merchant_key": "starbucks",     // normalized merchant (see below)
  "category": "Dining",            // the user's chosen category
  "updated_at": "2026-07-19T13:00:00Z"
}
```

- Deterministic `_id` (`catrule:<user_id>:<merchant_key>`) means correcting the
  same merchant again is an idempotent **upsert**, not a duplicate — exactly like
  the existing expense `make_id()` pattern.
- No schema migration needed: Cloudant is schemaless and `query_expenses()`
  already filters to expense docs via `type != "user"`; we simply add another
  filtered query for `type == "category_rule"`.

## Merchant normalization (`merchant_key`)

To match "identical/similar" expenses reliably, normalize the merchant string
before matching or storing:

- lowercase, strip surrounding whitespace;
- collapse repeated spaces;
- drop trailing store/transaction noise (numbers, `#1234`, city codes, `POS`,
  dates) with a simple regex;
- keep the core brand token(s), e.g. `"STARBUCKS #1234 MONTREAL"` → `starbucks`.

Put this in `schema.py` as `normalize_merchant(merchant) -> str` so both the
write path (creating a rule) and the read path (applying rules during ingest)
use the exact same key.

## Applying rules during ingest (the "stays with this category" part)

`pipeline.process_file()` already collects the AI's expense dicts from
`router.route()` before it calls `store.upsert_expense()`. Insert a rule-apply
step in between:

```python
# pipeline.process_file() — after router.route(), before upsert loop
rules = store.get_category_rules(user_id)          # {merchant_key: category}
for doc in expenses:
    key = schema.normalize_merchant(doc["merchant"])
    if key in rules:
        doc["category"] = rules[key]               # user override wins over AI
    store.upsert_expense(doc)
```

- Rules are loaded **once per upload** (one Mango query), then applied in memory —
  negligible cost.
- The override happens after `build_expense()` has already validated the AI's
  category, so the final stored category is the user's remembered choice.
- Because the AI still runs first, brand-new merchants (no rule yet) keep getting
  AI categorization; only known merchants are pinned.

## Re-categorization write path (user corrects an expense)

Add a backend endpoint, e.g. `PATCH /api/expenses/{id}`:

1. Load the expense (enforce it belongs to `user["id"]`).
2. Set `category` to the new value (validate against the current category list).
3. Upsert the expense (immediate fix).
4. Upsert a `category_rule` doc for `normalize_merchant(expense.merchant)` →
   new category (the "remember this" step).

```python
@router.patch("/expenses/{expense_id}")
def recategorize(expense_id: str, body: CategoryIn, user=Depends(current_user)):
    doc = store.get_expense(user_id=user["id"], expense_id=expense_id)
    doc["category"] = coerce_category(body.category)
    store.upsert_expense(doc)
    store.upsert_category_rule(
        user_id=user["id"],
        merchant_key=normalize_merchant(doc["merchant"]),
        category=doc["category"],
    )
    return {"ok": True, "expense": doc}
```

Optionally, when a rule is created you can also **back-apply** it to the user's
existing expenses with the same `merchant_key`, so past transactions are
recategorized too (a single Mango query + bulk upsert).

## New `store.py` helpers

Mirror the existing `get_categories` / `set_categories` / `query_expenses` style:

```python
_CATRULE_PREFIX = "catrule:"

def get_category_rules(user_id) -> dict:
    """Return {merchant_key: category} for one user."""
    docs = query_expenses(user_id=user_id,
                          selector={"type": "category_rule"})
    return {d["merchant_key"]: d["category"] for d in docs if d.get("merchant_key")}

def upsert_category_rule(user_id, merchant_key, category) -> None:
    doc_id = f"{_CATRULE_PREFIX}{user_id}:{merchant_key}"
    # GET for _rev then PUT — same upsert pattern as upsert_expense()
    ...
```

(Reuse the existing `_find` + `_ensure_db` + IAM-token machinery already in
`store.py`; add `type` to the Mango selector. `delete_user_expenses()` should
also delete `category_rule` docs on Reset DB if you want a full wipe.)

## Frontend changes

In `Dashboard.jsx`, render the expense table's Category cell as an editable
dropdown (options come from the existing `/api/categories`). On change:

```js
await api.recategorize(expense.id, newCategory);
// then refresh /summary + /expenses so the pie chart and tables update
```

Add to `api.js`:

```js
recategorize: (id, category) =>
  request(`/expenses/${id}`, { method: "PATCH", body: { category } }),
```

A small "learned ✓" hint or toast reassures the user the choice will be remembered.

## Why this approach (vs. alternatives)

- **Override rules (recommended):** instant, deterministic, per-user, cheap,
  fully reversible, and reuses the current Cloudant + pipeline patterns. No model
  cost or latency.
- **Prompt injection of known mappings:** feed the user's rules into the Granite/
  vision system prompt as "known merchant→category hints." Softer (the model may
  still deviate) and grows the prompt; use only as a complement, not the source of
  truth.
- **Fine-tuning / distillation:** overkill for per-user preferences — expensive,
  slow to update, not per-user, and hard to reverse. Not recommended here.

## Edge cases & limitations

- **Merchant collisions:** overly aggressive normalization could merge distinct
  merchants. Keep the regex conservative; store the original merchant on the
  expense (unchanged) so nothing is lost.
- **Ambiguous merchants** (e.g. a superstore that is sometimes Groceries,
  sometimes Shopping): a merchant-only rule always picks one category. If needed,
  extend the rule key later with an amount band or keyword without changing the
  overall design.
- **Deleted categories:** if a user removes a category that a rule points to,
  fall back to `Other` (reuse `coerce_category`) or prune orphaned rules.
- **Deposits:** rules apply only to expenses (`flow == "withdrawal"`); leave the
  deposit path untouched.

## Implementation checklist

1. `schema.py`: add `normalize_merchant()`.
2. `store.py`: add `get_category_rules()` and `upsert_category_rule()`; extend
   `delete_user_expenses()` to also remove rules.
3. `pipeline.py`: load rules once and override categories before upserting.
4. `web/backend/routes_expenses.py`: add `PATCH /expenses/{id}` (update expense +
   upsert rule; optional back-apply to existing expenses).
5. `web/frontend/src/api.js`: add `recategorize()`.
6. `web/frontend/src/pages/Dashboard.jsx`: editable category dropdown per row,
   refresh summary/expenses after a change.
7. Rebuild the frontend (`npm run build`) and verify: change a category, re-upload
   the same file, confirm the new category sticks automatically.
