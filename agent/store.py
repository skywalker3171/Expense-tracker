"""store.py - Cloudant (direct IAM REST) + COS (boto3)."""
from __future__ import annotations
import logging, mimetypes, os, time
import boto3, requests, config
log = logging.getLogger(__name__)
_IAM_URL = "https://iam.cloud.ibm.com/identity/token"
_tok = {"t": None, "exp": 0.0}

def _iam_token() -> str:
    if time.time() < _tok["exp"] - 60 and _tok["t"]:
        return _tok["t"]
    r = requests.post(_IAM_URL, data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": config.CLOUDANT_APIKEY}, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    r.raise_for_status()
    j = r.json()
    _tok["t"] = j["access_token"]
    _tok["exp"] = time.time() + j.get("expires_in", 3600)
    return _tok["t"]

_BASE = config.CLOUDANT_URL.rstrip("/")
_db_ready = False

def _headers() -> dict:
    return {"Authorization": "Bearer " + _iam_token(), "Content-Type": "application/json"}

def _ensure_db() -> None:
    global _db_ready
    if _db_ready:
        return
    url = _BASE + "/" + config.CLOUDANT_DB
    r = requests.put(url, headers=_headers(), timeout=30)
    if r.status_code not in (201, 202, 412):
        log.warning("ensure_db %s -> %s %s", config.CLOUDANT_DB, r.status_code, r.text[:200])
    _db_ready = True

def upsert_expense(doc):
    _ensure_db()
    doc_id = doc.get("id")
    url = _BASE + "/" + config.CLOUDANT_DB + "/" + doc_id
    g = requests.get(url, headers=_headers(), timeout=30)
    document = dict(doc)
    document["_id"] = doc_id
    if g.status_code == 200:
        document["_rev"] = g.json().get("_rev")
    r = requests.put(url, headers=_headers(), json=document, timeout=30)
    if r.status_code not in (201, 202):
        log.error("upsert failed %s %s %s", doc_id, r.status_code, r.text)
        r.raise_for_status()
    log.debug("Upserted %s", doc_id)

def _ensure_user_index():
    """Create a Mango index on user_id (+ date) so per-user queries are fast."""
    url = _BASE + "/" + config.CLOUDANT_DB + "/_index"
    body = {
        "index": {"fields": ["user_id", "date"]},
        "name": "user_id-date-index",
        "type": "json",
    }
    r = requests.post(url, headers=_headers(), json=body, timeout=30)
    if r.status_code not in (200, 201):
        log.warning("ensure_user_index -> %s %s", r.status_code, r.text[:200])


def query_expenses(user_id, selector=None):
    """Return expenses for a single user only. user_id is always enforced."""
    _ensure_db()
    _ensure_user_index()
    mango = dict(selector or {})
    mango["user_id"] = user_id
    # Never return non-expense docs (e.g. the user's own account doc, which
    # shares the same user_id). Excluding type=="user" keeps legacy expense
    # docs (which may lack a type field) while dropping account docs.
    mango.setdefault("type", {"$ne": "user"})
    url = _BASE + "/" + config.CLOUDANT_DB + "/_find"
    body = dict(selector=mango, limit=10000)
    r = requests.post(url, headers=_headers(), json=body, timeout=60)
    if r.status_code != 200:
        log.error("query failed %s %s", r.status_code, r.text)
        return list()
    return r.json().get("docs", list())


def delete_user_expenses(user_id) -> int:
    """Delete all expense docs for a single user. Returns the count deleted."""
    docs = query_expenses(user_id=user_id)
    if not docs:
        return 0
    deletions = [
        {"_id": d["_id"], "_rev": d["_rev"], "_deleted": True}
        for d in docs
        if d.get("_id") and d.get("_rev")
    ]
    if not deletions:
        return 0
    url = _BASE + "/" + config.CLOUDANT_DB + "/_bulk_docs"
    r = requests.post(url, headers=_headers(), json={"docs": deletions}, timeout=60)
    if r.status_code not in (200, 201):
        log.error("delete_user_expenses failed %s %s", r.status_code, r.text)
        r.raise_for_status()
    log.info("Deleted %d expenses for user %s", len(deletions), user_id)
    return len(deletions)


#
# ---------------------------------------------------------------------------
_CATEGORIES_DOC_ID = "settings:categories"


def get_categories() -> list:
    """Return the editable global category list, falling back to config defaults."""
    _ensure_db()
    url = _BASE + "/" + config.CLOUDANT_DB + "/" + _CATEGORIES_DOC_ID
    r = requests.get(url, headers=_headers(), timeout=30)
    if r.status_code == 200:
        cats = r.json().get("categories")
        if isinstance(cats, list) and cats:
            return cats
    return list(config.CATEGORIES)


def set_categories(categories: list) -> list:
    """Persist the editable global category list. Returns the saved list."""
    _ensure_db()
    cleaned = [str(c).strip() for c in categories if str(c).strip()]
    # de-dup while preserving order
    seen = set()
    cleaned = [c for c in cleaned if not (c in seen or seen.add(c))]
    url = _BASE + "/" + config.CLOUDANT_DB + "/" + _CATEGORIES_DOC_ID
    document = {"_id": _CATEGORIES_DOC_ID, "type": "settings", "categories": cleaned}
    g = requests.get(url, headers=_headers(), timeout=30)
    if g.status_code == 200:
        document["_rev"] = g.json().get("_rev")
    r = requests.put(url, headers=_headers(), json=document, timeout=30)
    if r.status_code not in (201, 202):
        log.error("set_categories failed %s %s", r.status_code, r.text)
        r.raise_for_status()
    return cleaned


def _cos_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("COS_ENDPOINT", config.COS_ENDPOINT),
        aws_access_key_id=os.environ.get("COS_HMAC_ACCESS_KEY"),
        aws_secret_access_key=os.environ.get("COS_HMAC_SECRET_KEY"),
        region_name="us-south",
    )


def upload_attachment(user_id, source_ref, filename, data):
    key = user_id + "/" + source_ref + "/" + filename
    ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    _cos_client().put_object(Bucket=config.COS_BUCKET, Key=key, Body=data, ContentType=ctype)
    log.info("Uploaded %s to COS bucket %s", key, config.COS_BUCKET)
    return key
