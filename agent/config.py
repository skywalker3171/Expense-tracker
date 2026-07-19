"""
config.py — load all secrets from environment variables.
In local dev: secrets live in ../Infra/secrets.env and are loaded via
python-dotenv at process start (see main.py), or export them manually:
    export $(cat ../Infra/secrets.env | grep -v ^# | xargs)
In Code Engine: secrets are injected via --env-from-secret expense-secrets.
"""

import os


def _require(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise EnvironmentError(f"Required env var '{key}' is not set.")
    return val


# Gmail OAuth
GMAIL_CLIENT_ID      = _require("GMAIL_CLIENT_ID")
GMAIL_CLIENT_SECRET  = _require("GMAIL_CLIENT_SECRET")
GMAIL_REFRESH_TOKEN  = _require("GMAIL_REFRESH_TOKEN")

# watsonx.ai
WATSONX_APIKEY      = _require("WATSONX_APIKEY")
WATSONX_PROJECT_ID  = _require("WATSONX_PROJECT_ID")
WATSONX_URL         = os.environ.get("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")

# IBM Cloud Object Storage
COS_APIKEY          = _require("COS_APIKEY")
COS_ENDPOINT        = os.environ.get("COS_ENDPOINT", "https://s3.us-south.cloud-object-storage.appdomain.cloud")
COS_HMAC_ACCESS_KEY = _require("COS_HMAC_ACCESS_KEY")
COS_HMAC_SECRET_KEY = _require("COS_HMAC_SECRET_KEY")
COS_BUCKET          = os.environ.get("COS_BUCKET", "expense-receipts-raw-jb")

# Cloudant
CLOUDANT_URL    = _require("CLOUDANT_URL")
CLOUDANT_APIKEY = _require("CLOUDANT_APIKEY")
CLOUDANT_DB     = os.environ.get("CLOUDANT_DB", "expenses")

# Identity of the connected Gmail mailbox owner. Expenses ingested via the
# Gmail poller are attributed to this user_id. The web app supplies its own
# per-request user_id instead.
GMAIL_USER_ID   = os.environ.get("GMAIL_USER_ID", "gmail-mailbox-owner")

# Web / auth config (used by web/backend).
# JWT_SECRET signs auth tokens; a weak/default value makes every token forgeable,
# so it must be provided explicitly and must not be a known insecure placeholder.
_INSECURE_JWT_SECRETS = {"", "dev-insecure-change-me", "change-me", "secret"}
JWT_SECRET      = os.environ.get("JWT_SECRET", "")
if JWT_SECRET in _INSECURE_JWT_SECRETS or len(JWT_SECRET) < 16:
    raise EnvironmentError(
        "JWT_SECRET must be set to a strong, non-default value (>= 16 chars). "
        "Set it via the environment / a secrets manager before starting the app."
    )

MAX_UPLOAD_MB   = int(os.environ.get("MAX_UPLOAD_MB", "10"))
# Comma-separated allow-list of browser origins. Defaults to empty (deny) so a
# forgotten config does not silently allow every site; set explicitly in prod.
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "")

# Expense categories (fixed list — models must map to one of these)
CATEGORIES = [
    "Groceries", "Dining", "Transport", "Utilities",
    "Housing", "Health", "Entertainment", "Shopping", "Travel", "Other",
]
