# Security Hardening — Expense Tracker

This document reviews the security posture of the Expense Tracker (the shared
`agent/` core, the `web/backend` FastAPI service, and the `web/frontend` React
SPA) and recommends concrete hardening measures.

Per the project's all-IBM stance, **IBM Cloud services are recommended first**
for each concern; each section also lists the **code changes** that should be
made regardless of whether the managed service is adopted.

Findings are ordered roughly by severity/impact.

---

## Threat model summary

- **Assets:** user financial data (expenses, deposits) in Cloudant, raw receipt
  files in COS, user credentials (bcrypt hashes), and third-party secrets
  (watsonx API key, COS HMAC keys, Cloudant IAM key, Gmail OAuth refresh token).
- **Entry points:** public web upload/query API, JWT-authenticated dashboard
  routes, the Gmail poller, and the LLM prompt paths (uploaded content + NL query).
- **Trust boundaries:** browser to FastAPI, FastAPI to IBM Cloud services, and the Gmail MCP server to the agent.

---

## 1. Secrets management (Critical)

### Findings
> **Status:** ✅ *Partially implemented.* `JWT_SECRET` no longer has an insecure default — `agent/config.py` now requires it and fails fast on startup if it is unset, shorter than 16 chars, or a known placeholder. The remaining items below (Secrets Manager, IAM bindings, rotation) are still recommended.

- `config.JWT_SECRET` defaults to the hardcoded value `"dev-insecure-change-me"`. If the env var is unset in production, all JWTs are forgeable and any user can be impersonated.
- Secrets are loaded from a plaintext file `Infra/secrets.env` via `python-dotenv` (see `agent/main.py`, `web/backend/app.py`). Plaintext at-rest secrets are easy to leak (backups, laptops, accidental commits).
- COS uses long-lived static HMAC access/secret keys; watsonx and Cloudant use static IAM API keys. None rotate.
- The Gmail `GMAIL_REFRESH_TOKEN` is a long-lived credential granting mailbox access.

### IBM Cloud services (preferred)
- **IBM Secrets Manager** — store the JWT signing secret, watsonx API key, COS HMAC keys, Cloudant IAM key, and the Gmail refresh token as managed secrets. Inject them at runtime; enable automatic rotation for supported credential types.
- **IBM Cloud IAM + Trusted Profiles / Code Engine service bindings** — bind Cloudant and COS to the Code Engine app via IAM so the app receives short-lived, automatically-rotated credentials instead of static keys in a file.
- **IBM Key Protect / Hyper Protect Crypto Services** — back the JWT signing key with a managed KMS key rather than a plaintext string.

### Code changes
- Remove the insecure default: `JWT_SECRET` must be required (raise on startup if unset) using the existing `_require()` helper in `agent/config.py`, never defaulted to a literal.
- Never bake secrets into the image (already respected by `.dockerignore`); fetch from Secrets Manager at boot rather than mounting `Infra/secrets.env`.
- Add a startup assertion that refuses to run in production if `JWT_SECRET` is short/weak or equals a known default.
- Ensure `Infra/secrets.env` is git-ignored and add secret-scanning (see section 10).
- Prefer IBM SDKs that support IAM API-key auth for COS instead of static HMAC keys where possible.

---

## 2. CORS misconfiguration (High)

### Findings
> **Status:** ✅ *Implemented.* `web/backend/app.py` no longer combines a wildcard origin with credentials. Since auth uses bearer tokens, `allow_credentials=False`; `allow_methods`/`allow_headers` are scoped to the verbs and `Authorization`/`Content-Type` the SPA uses; and `ALLOWED_ORIGINS` defaults to empty (deny) in `agent/config.py`.


### IBM Cloud services (preferred)
- **IBM Cloud Internet Services (CIS)** or **API Connect** in front of the app to centrally enforce allowed origins, WAF rules, and rate limits before requests reach FastAPI.

### Code changes
- Default `ALLOWED_ORIGINS` to the empty set (deny) rather than `*`; require an explicit allow-list in production.
- Never combine `allow_origins=["*"]` with `allow_credentials=True`. Since auth is a bearer token (not cookies), set `allow_credentials=False`.
- Restrict `allow_methods` and `allow_headers` to the specific verbs/headers the SPA uses instead of `*`.

---

## 3. Authentication and JWT handling (High)

### Findings
- Tokens use `HS256` with a 7-day TTL (`deps.py`) and there is no refresh, rotation, logout, or revocation mechanism. A leaked token is valid for a week.
- The SPA stores the JWT in `localStorage` (`web/frontend/src/api.js`), which is readable by any injected script (XSS), making token theft high-impact.
- There is no rate limiting or lockout on `/api/auth/login` or `/api/auth/register`, enabling credential stuffing and brute force.
- No password strength policy is enforced; any password is accepted and silently truncated to 72 bytes in `users.py`.
- Login and registration return distinct behavior that can leak whether an email is registered (registration returns 409 conflict), enabling user enumeration.

### IBM Cloud services (preferred)
- **IBM Cloud App ID** — offload authentication entirely: managed sign-up/sign-in, MFA, password policies, token issuance/revocation, and social/enterprise identity. This replaces the hand-rolled JWT/bcrypt flow with a hardened, standards-based OIDC provider.
- **API Connect / CIS rate limiting** — throttle auth endpoints at the edge to blunt brute-force and enumeration.

### Code changes
- Shorten access-token TTL (e.g. 15-60 minutes) and add a refresh-token flow with server-side revocation (a token version/`jti` denylist in Cloudant).
- Prefer storing the token in an httpOnly, Secure, SameSite cookie over `localStorage` to reduce XSS token theft; if cookies are used, add CSRF protection.
- Add per-IP and per-account rate limiting and exponential backoff/lockout on login and registration (e.g. `slowapi`, or enforce at API Connect/CIS).
- Enforce a password policy (minimum length, complexity, and a breached-password check) and reject overly long inputs explicitly instead of silently truncating.
- Make register/login responses uniform to avoid user enumeration (generic error, constant-time behavior).
- Add `nbf`/`iss`/`aud` claims and validate them on decode; consider RS256/ES256 with a KMS-managed key so the signing key never lives in app memory as a plain string.

---

## 4. File upload handling (High)

### Findings
- `routes_upload.py` reads the entire file into memory (`await file.read()`) before checking the size limit, so a large upload consumes memory before the `MAX_UPLOAD_MB` guard fires (DoS vector).
- File type is inferred from the client-supplied filename/extension and content-type (`router.route`), which are trivially spoofable; there is no magic-byte/content validation.
- Uploaded files are parsed by pdfplumber, pypdf, and Pillow, which have a history of parser vulnerabilities and can be targeted with malformed/zip-bomb-style inputs; there is no sandboxing or resource limiting on parsing.
- No malware scanning is performed before storing raw files in COS.

### IBM Cloud services (preferred)
- **IBM Cloud Object Storage pre-signed uploads** — have the browser upload directly to COS via a short-lived pre-signed URL so untrusted bytes never transit (or exhaust) the API process; the backend then processes from COS.
- **IBM Code Engine per-request resource limits / concurrency caps** — bound memory and CPU so a single large or malicious file cannot exhaust the instance.
- **Malware scanning** — scan uploads (e.g. a ClamAV sidecar or a scanning step) before parsing/persisting.

### Code changes
- Enforce the size limit while streaming (reject once the byte count exceeds the limit) instead of after fully buffering; validate `Content-Length` early.
- Validate real file type by inspecting magic bytes (e.g. `python-magic`) and reject anything not on an explicit allow-list; do not trust the extension or client content-type.
- Run PDF/image parsing with strict limits (max pages, max pixels/`Image.MAX_IMAGE_PIXELS`, timeouts) and treat parser exceptions as rejects.
- Sanitize/namespace COS object keys (already namespaced by `user_id`); ensure filenames cannot inject path traversal into the key.
- Set restrictive content types and never serve raw uploaded files back inline without `Content-Disposition: attachment`.

---

## 5. Data isolation and access control (High)

### Findings
> **Status:** ✅ *Partially implemented.* Categories are now **per-user**: `store.get_categories`/`set_categories` key the settings doc by `user_id` and the routes in `routes_expenses.py` pass the caller's id, so one user can no longer overwrite the shared/global category list. The remaining items below (DB-level scoping, cross-tenant tests, opaque ids) are still recommended.

- Tenant isolation is enforced only in application code (`store.query_expenses` injects `user_id`, `get_expense` checks ownership). A missed filter in any new query would leak cross-user data; there is no database-level guarantee.
- The category list is **global**: `GET/PUT /api/categories` (`routes_expenses.py`, `store.set_categories`) lets any authenticated user overwrite the shared category settings doc for everyone. This is a cross-tenant integrity issue.
- All data (every tenant plus user records) lives in a single Cloudant database accessed with one broad IAM API key; a compromised app key exposes all tenants.
- `get_expense` fetches a doc by id before checking ownership, so document ids are directly addressable (mitigated by the ownership check, but still worth constraining).

### IBM Cloud services (preferred)
- **IBM Cloudant fine-grained access / separate databases per concern** — isolate user-credential docs from expense docs, and consider per-tenant partitioning (Cloudant partitioned databases keyed by `user_id`) so queries are scoped at the storage layer.
- **IBM Cloud IAM scoped service IDs** — use least-privilege service credentials (read/write only to the specific database), not an account-wide key.

### Code changes
- Make categories **per-user**: key the settings doc by `user_id` (like `catrule:`), so one user cannot mutate another's or the global category list.
- Add a single choke-point helper that always injects `user_id` into every selector and assert ownership on every read/write, so no route can accidentally skip the filter.
- Add automated tests that a second user cannot read, update, or delete another user's expenses, deposits, category rules, or settings.
- Consider non-enumerable/opaque document ids and rate-limit id-addressable lookups.

---

## 6. Prompt injection and LLM handling (Medium)

### Findings
- Uploaded file content and the natural-language query text are inserted directly into LLM prompts (`watsonx_client.categorize_text`, `parse_query`, `parse_image_receipt`). A crafted receipt/CSV/query could attempt prompt injection to influence categorization or coax unexpected output.
- LLM output is parsed leniently (`_extract_json` salvages partial JSON). While `schema.coerce_*` normalizes fields, category and amount handling should be strictly validated against the allow-list.
- watsonx errors log `resp.text[:500]` which could include sensitive prompt/response fragments.

### IBM Cloud services (preferred)
- **watsonx.ai guardrails / watsonx.governance** — apply input/output moderation and content filters, and monitor model behavior for drift or abuse.

### Code changes
- Treat all model output as untrusted: strictly coerce `category` to the allowed list, `amount` to a bounded number, and dates to valid ISO before persisting.
- Keep untrusted content clearly delimited from instructions in prompts and avoid echoing model output into other privileged actions.
- Cap `max_new_tokens` and input length; reject or truncate oversized text before sending to the model.
- Avoid logging raw model responses/prompts at INFO; redact and log at DEBUG only.

---

## 7. Transport, HTTP headers, and network (Medium)

### Findings
- No HTTPS/TLS enforcement or HSTS is configured in the app; TLS is assumed to be terminated upstream.
- No security response headers are set (CSP, `X-Content-Type-Options`, `X-Frame-Options`/frame-ancestors, `Referrer-Policy`, `Permissions-Policy`).
- The SPA catch-all route serves files from disk based on the request path (`app.py spa()`); path handling should be verified against traversal.

### IBM Cloud services (preferred)
- **IBM Cloud Internet Services (CIS)** — TLS, HSTS, WAF, DDoS protection, and edge caching in front of the Code Engine app.
- **IBM Code Engine** — provides a managed HTTPS endpoint; enforce HTTPS-only.

### Code changes
- Add a middleware to set security headers on all responses: `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, a restrictive `Content-Security-Policy`, `X-Frame-Options: DENY`/`frame-ancestors 'none'`, `Referrer-Policy: no-referrer`, and a minimal `Permissions-Policy`.
- Redirect HTTP to HTTPS (or reject non-TLS) and set the `Secure` flag on any cookies.
- Verify the SPA static-file handler normalizes/validates the path so `../` traversal cannot escape `FRONTEND_DIST_DIR`.

---

## 8. Data protection and privacy (Medium)

### Findings
- Raw receipt files (which may contain full account numbers, income, and PII) are stored in COS with no stated encryption-at-rest configuration, lifecycle expiry, or retention policy.
- Deposit obfuscation is a display-time transformation; the underlying data handling should still assume the stored data is sensitive financial PII.
- There is no documented account deletion / data-export (GDPR-style) capability beyond the demo `reset` of expenses.

### IBM Cloud services (preferred)
- **IBM Key Protect + COS/Cloudant KYOK/BYOK encryption** — enable customer-managed keys for encryption at rest of both the object store and the database.
- **IBM Cloud Object Storage lifecycle & retention policies** — auto-expire or archive raw receipts and optionally enable WORM/retention for compliance.
- **IBM Cloud Security and Compliance Center** — continuously assess the account against a financial-data compliance profile.

### Code changes
- Add a documented retention/deletion path: deleting a user should remove their Cloudant docs and COS objects (extend `delete_user_expenses` to also purge COS keys under `{user_id}/`).
- Consider whether raw files need to be retained at all after extraction; if not, delete them or set short lifecycle expiry.

---

## 9. Container and deployment hardening (Medium)

### Findings
- The runtime image (`web/Dockerfile`) runs as root (no `USER` directive) and installs build/runtime OS packages without pinning.
- No image vulnerability scanning is referenced in the build/deploy flow.
- The API also runs the Gmail poller path which uses `tempfile` and an MCP server; the trust of the MCP server and its OAuth token should be scoped.

### IBM Cloud services (preferred)
- **IBM Cloud Container Registry + Vulnerability Advisor** — push the image to ICR and gate deploys on scan results.
- **IBM Code Engine** — run with least privilege, set CPU/memory limits, and inject secrets via bound services rather than a mounted env file.

### Code changes
- Add a non-root `USER` to the Dockerfile and run the process unprivileged; make the filesystem read-only where possible.
- Pin base images by digest and pin OS/pip package versions; rebuild regularly to pick up patches.
- Scope the Gmail MCP OAuth token to the minimum required scopes and treat MCP responses as untrusted input (already parsed defensively in `gmail_client.py`).

---

## 10. Supply chain, logging, and observability (Low/Medium)

### Findings
- No dependency vulnerability scanning or lockfile-pinned Python dependencies are referenced.
- No secret-scanning is configured to prevent committing `secrets.env` or keys.
- Logging is at INFO globally and may include sensitive fragments (email subjects/senders in `main.py`, model output, upstream error bodies). No audit trail for auth or data-access events.

### IBM Cloud services (preferred)
- **IBM Cloud Log Analysis / Activity Tracker** — centralize application logs and capture an audit trail of security-relevant events (auth, data access, admin actions).
- **IBM Cloud Monitoring** — alert on anomalies (spikes in 401s, upload volume, error rates).

### Code changes
- Pin and hash-lock Python dependencies (`requirements.txt` with pinned versions / a lockfile) and enable automated dependency and CVE scanning in CI.
- Add secret-scanning (e.g. `gitleaks`/`detect-secrets`) as a pre-commit hook and CI gate.
- Reduce log verbosity for sensitive data; redact PII, tokens, and upstream error bodies; emit structured audit events for login, logout, upload, recategorize, reset, and category changes.

---

## Priority summary

| # | Area | Severity | Top action |
| --- | --- | --- | --- |
| 1 | Secrets management | Critical | Remove `JWT_SECRET` default; use IBM Secrets Manager + IAM bindings |
| 2 | CORS | High | No wildcard origin with credentials; explicit allow-list |
| 3 | Auth / JWT | High | IBM App ID or short-lived tokens + rate limiting + move token off `localStorage` |
| 4 | File upload | High | Stream size limits, magic-byte validation, sandboxed parsing, malware scan |
| 5 | Data isolation | High | Per-user categories, DB-level scoping, cross-tenant tests |
| 6 | LLM / prompt injection | Medium | Strict output validation, watsonx guardrails, input caps |
| 7 | Transport / headers | Medium | CIS/WAF, HSTS, CSP and other security headers |
| 8 | Data protection | Medium | Key Protect BYOK, COS lifecycle/retention, deletion path |
| 9 | Container / deploy | Medium | Non-root image, pinned deps, ICR Vulnerability Advisor |
| 10 | Supply chain / logging | Low/Medium | Dependency + secret scanning, redacted logs, Activity Tracker audit |

### Recommended sequencing
1. Immediately: remove the `JWT_SECRET` default and fix the CORS wildcard-with-credentials combination (both are quick, high-impact code changes).
2. Short term: move secrets to IBM Secrets Manager / IAM bindings, add auth rate limiting, and tighten upload validation.
3. Medium term: adopt IBM Cloud App ID for authentication, per-user categories with DB-level scoping, security headers behind CIS, and BYOK encryption.
4. Ongoing: dependency/secret scanning, non-root hardened image, and centralized audit logging via Activity Tracker.

> Note: the current design already does several things well — a shared, single-responsibility pipeline; per-request `user_id` scoping via a `current_user` dependency; deterministic idempotent document ids; bcrypt password hashing; defensive LLM JSON parsing; and keeping secrets out of the image via `.dockerignore`. The items above build on that foundation.
