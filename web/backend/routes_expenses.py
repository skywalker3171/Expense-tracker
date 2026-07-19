"""
routes_expenses.py — per-user expense list, category summary, and chart PNG.
Deposits (flow == "deposit") are kept separate from spending expenses.
"""
from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

import chart
import store
import watsonx_client
from schema import coerce_category, normalize_merchant
from deps import current_user

router = APIRouter()


class CategoriesIn(BaseModel):
    categories: list[str]


class CategoryIn(BaseModel):
    category: str


class QueryIn(BaseModel):
    q: str


@router.get("/categories")
def get_categories(user=Depends(current_user)):
    return {"categories": store.get_categories(user_id=user["id"])}


@router.put("/categories")
def put_categories(body: CategoriesIn, user=Depends(current_user)):
    saved = store.set_categories(body.categories, user_id=user["id"])
    return {"categories": saved}


def _is_deposit_doc(e) -> bool:
    return str(e.get("flow", "")).strip().lower() == "deposit"


@router.get("/expenses")
def list_expenses(user=Depends(current_user)):
    docs = store.query_expenses(user_id=user["id"])
    expenses = [e for e in docs if not _is_deposit_doc(e)]
    deposits = [e for e in docs if _is_deposit_doc(e)]
    expenses.sort(key=lambda e: e.get("date", ""), reverse=True)
    deposits.sort(key=lambda e: e.get("date", ""), reverse=True)
    return {
        "count": len(expenses),
        "expenses": expenses,
        "deposit_count": len(deposits),
        "deposits": deposits,
    }


@router.get("/summary")
def summary(user=Depends(current_user)):
    docs = store.query_expenses(user_id=user["id"])
    expenses = [e for e in docs if not _is_deposit_doc(e)]
    totals: dict[str, float] = defaultdict(float)
    for e in expenses:
        totals[e.get("category", "Other")] += float(e.get("amount", 0) or 0)
    grand_total = round(sum(totals.values()), 2)
    return {
        "total": grand_total,
        "count": len(expenses),
        "by_category": {k: round(v, 2) for k, v in sorted(totals.items())},
    }


@router.patch("/expenses/{expense_id}")
def recategorize(expense_id: str, body: CategoryIn, user=Depends(current_user)):
    """Change one expense's category and remember the choice for this merchant.

    The saved rule is applied to future uploads (in pipeline.process_file) and is
    also back-applied to the user's existing expenses with the same merchant.
    """
    doc = store.get_expense(user_id=user["id"], expense_id=expense_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Expense not found")
    if _is_deposit_doc(doc):
        raise HTTPException(status_code=400, detail="Cannot categorize a deposit")

    new_category = coerce_category(body.category)
    doc["category"] = new_category
    store.upsert_expense(doc)

    merchant_key = normalize_merchant(doc.get("merchant", ""))
    if merchant_key:
        store.upsert_category_rule(
            user_id=user["id"],
            merchant_key=merchant_key,
            category=new_category,
        )
        # Back-apply to the user's existing expenses with the same merchant.
        for other in store.query_expenses(user_id=user["id"]):
            if _is_deposit_doc(other):
                continue
            if other.get("id") == expense_id:
                continue
            if normalize_merchant(other.get("merchant", "")) == merchant_key \
                    and other.get("category") != new_category:
                other["category"] = new_category
                store.upsert_expense(other)

    return {"ok": True, "expense": doc, "merchant_key": merchant_key}


@router.post("/reset")
def reset_db(user=Depends(current_user)):
    """Flush the current user's expense data (demo reset)."""
    deleted = store.delete_user_expenses(user_id=user["id"])
    return {"deleted": deleted}


def _apply_filter(expenses, cats, date_from, date_to):
    cats_lower = {c.strip().lower() for c in (cats or []) if c}
    out = []
    for e in expenses:
        if cats_lower and str(e.get("category", "")).strip().lower() not in cats_lower:
            continue
        d = str(e.get("date", ""))
        if date_from and d < date_from:
            continue
        if date_to and d > date_to:
            continue
        out.append(e)
    return out


@router.post("/query")
def query(body: QueryIn, user=Depends(current_user)):
    """Natural-language filter: parse the query, then return a filtered summary + rows."""
    q = (body.q or "").strip()
    flt = {"categories": [], "date_from": None, "date_to": None}
    if q:
        try:
            flt = watsonx_client.parse_query(text=q)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Query parsing failed: {exc}")

    docs = store.query_expenses(user_id=user["id"])
    expenses = [e for e in docs if not _is_deposit_doc(e)]
    filtered = _apply_filter(expenses, flt.get("categories"),
                             flt.get("date_from"), flt.get("date_to"))
    filtered.sort(key=lambda e: e.get("date", ""), reverse=True)

    totals: dict[str, float] = defaultdict(float)
    for e in filtered:
        totals[e.get("category", "Other")] += float(e.get("amount", 0) or 0)

    return {
        "filter": flt,
        "total": round(sum(totals.values()), 2),
        "count": len(filtered),
        "by_category": {k: round(v, 2) for k, v in sorted(totals.items())},
        "expenses": filtered,
    }


@router.get("/chart.png")
def chart_png(user=Depends(current_user)):
    docs = store.query_expenses(user_id=user["id"])
    expenses = [e for e in docs if not _is_deposit_doc(e)]
    png = chart.build_pie_chart(expenses)
    return Response(content=png, media_type="image/png")
