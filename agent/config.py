"""
config.py — load all secrets from environment variables.
In local dev: `export $(cat ../secrets.env | grep -v ^# | xargs)` before running.
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

# Expense categories (fixed list — models must map to one of these)
CATEGORIES = [
    "Groceries", "Dining", "Transport", "Utilities",
    "Housing", "Health", "Entertainment", "Shopping", "Travel", "Other",
]
