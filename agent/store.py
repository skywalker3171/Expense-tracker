"""store.py - Cloudant (direct IAM REST) + COS (boto3)."""
from __future__ import annotations
import logging, mimetypes, os, time
from datetime import datetime, timezone
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
        log.warning("ensure_db %s -> %s", config.CLOUDANT_DB, r.status_code)
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

def _ensure_user_index():
    url = _BASE + "/" + config.CLOUDANT_DB + "/_index"
    body = {"index": {"fields": ["user_id", "date"]}, "name": "user_id-date-index", "type": "json"}
    r = requests.post(url, headers=_headers(), json=body, timeout=30)
    if r.status_code not in (200, 201):
        log.warning("ensure_user_index -> %s", r.status_code)

def query_expenses(user_id, selector=None):
    _ensure_db()
    _ensure_user_index()
    mango = dict(selector or {})
    mango["user_id"] = user_id
    mango.setdefault("type", "expense")
    url = _BASE + "/" + config.CLOUDANT_DB + "/_find"
    r = requests.post(url, headers=_headers(), json=dict(selector=mango, limit=10000), timeout=60)
    if r.status_code != 200:
        log.error("query failed %s %s", r.status_code, r.text)
        return list()
    return r.json().get("docs", list())

def get_expense(user_id, expense_id):
    _ensure_db()
    url = _BASE + "/" + config.CLOUDANT_DB + "/" + expense_id
    r = requests.get(url, headers=_headers(), timeout=30)
    if r.status_code != 200:
        return None
    doc = r.json()
    if doc.get("user_id") != user_id or doc.get("type") == "user":
        return None
    return doc

def delete_user_expenses(user_id) -> int:
    docs = query_expenses(user_id=user_id)
    docs += query_expenses(user_id=user_id, selector={"type": "category_rule"})
    deletions = [{"_id": d["_id"], "_rev": d["_rev"], "_deleted": True} for d in docs if d.get("_id") and d.get("_rev")]
    if not deletions:
        return 0
    url = _BASE + "/" + config.CLOUDANT_DB + "/_bulk_docs"
    r = requests.post(url, headers=_headers(), json={"docs": deletions}, timeout=60)
    if r.status_code not in (200, 201):
        log.error("delete_user_expenses failed %s %s", r.status_code, r.text)
        r.raise_for_status()
    return len(deletions)

_CATEGORIES_DOC_ID = "settings:categories"
_CATEGORIES_PREFIX = "settings:categories:"
_CATRULE_PREFIX = "catrule:"

def _categories_doc_id(user_id) -> str:
    # Per-user categories so one user cannot overwrite another's (or a shared
    # global) category list. Falls back to the legacy global doc id if no
    # user is supplied (e.g. the Gmail poller path).
    return _CATEGORIES_PREFIX + user_id if user_id else _CATEGORIES_DOC_ID

def get_category_rules(user_id) -> dict:
    docs = query_expenses(user_id=user_id, selector={"type": "category_rule"})
    return {d["merchant_key"]: d["category"] for d in docs if d.get("merchant_key") and d.get("category")}

def upsert_category_rule(user_id, merchant_key, category) -> None:
    _ensure_db()
    if not merchant_key:
        return
    doc_id = _CATRULE_PREFIX + user_id + ":" + merchant_key
    url = _BASE + "/" + config.CLOUDANT_DB + "/" + doc_id
    document = {"_id": doc_id, "type": "category_rule", "user_id": user_id, "merchant_key": merchant_key, "category": category, "updated_at": datetime.now(timezone.utc).isoformat()}
    g = requests.get(url, headers=_headers(), timeout=30)
    if g.status_code == 200:
        document["_rev"] = g.json().get("_rev")
    r = requests.put(url, headers=_headers(), json=document, timeout=30)
    if r.status_code not in (201, 202):
        log.error("upsert_category_rule failed %s %s", r.status_code, r.text)
        r.raise_for_status()

def get_categories(user_id=None) -> list:
    _ensure_db()
    url = _BASE + "/" + config.CLOUDANT_DB + "/" + _categories_doc_id(user_id)
    r = requests.get(url, headers=_headers(), timeout=30)
    if r.status_code == 200:
        cats = r.json().get("categories")
        if isinstance(cats, list) and cats:
            return cats
    return list(config.CATEGORIES)

def set_categories(categories: list, user_id=None) -> list:
    _ensure_db()
    cleaned = [str(c).strip() for c in categories if str(c).strip()]
    seen = set()
    cleaned = [c for c in cleaned if not (c in seen or seen.add(c))]
    doc_id = _categories_doc_id(user_id)
    url = _BASE + "/" + config.CLOUDANT_DB + "/" + doc_id
    document = {"_id": doc_id, "type": "settings", "user_id": user_id, "categories": cleaned}
    g = requests.get(url, headers=_headers(), timeout=30)
    if g.status_code == 200:
        document["_rev"] = g.json().get("_rev")
    r = requests.put(url, headers=_headers(), json=document, timeout=30)
    if r.status_code not in (201, 202):
        log.error("set_categories failed %s %s", r.status_code, r.text)
        r.raise_for_status()
    return cleaned

def _cos_client():
    return boto3.client("s3", endpoint_url=os.environ.get("COS_ENDPOINT", config.COS_ENDPOINT), aws_access_key_id=os.environ.get("COS_HMAC_ACCESS_KEY"), aws_secret_access_key=os.environ.get("COS_HMAC_SECRET_KEY"), region_name="us-south")

def upload_attachment(user_id, source_ref, filename, data):
    key = user_id + "/" + source_ref + "/" + filename
    ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    _cos_client().put_object(Bucket=config.COS_BUCKET, Key=key, Body=data, ContentType=ctype)
    log.info("Uploaded %s to COS bucket %s", key, config.COS_BUCKET)
    return key
