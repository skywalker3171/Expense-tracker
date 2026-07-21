# Project Coding Rules (Non-Obvious Only)
- Keep `config` imports late in tests: [`agent/test_smoke.py`](agent/test_smoke.py) preloads fake env vars before importing shared modules because [`agent/config.py`](agent/config.py) hard-fails on missing secrets.
- Preserve deterministic IDs from [`schema.make_id()`](agent/schema.py:30); changing `user_id`, `source_ref`, or `line_index` semantics breaks idempotent upserts.
- Use [`schema.normalize_merchant()`](agent/schema.py:101) for any merchant-based matching. Category learning in [`agent/pipeline.py`](agent/pipeline.py:41) and [`web/backend/routes_expenses.py`](web/backend/routes_expenses.py:79) depends on that exact normalization.
- Deposits are stored as normal expense docs with `flow="deposit"`; do not assume negative amounts or a separate collection.
- Frontend production behavior depends on a built [`web/frontend/dist`](web/frontend/dist); changes to SPA routing/assets should be verified through [`web/backend/app.py`](web/backend/app.py), not only Vite dev mode.
- No project lint/format hooks are configured. Match surrounding style instead of introducing formatter-driven rewrites.