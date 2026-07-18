"""
routes_expenses.py — per-user expense list, category summary, and chart PNG.
Deposits (flow == "deposit") are kept separate from spending expenses.
"""
from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel

import chart
import store
from deps import current_user

router = APIRouter()


class CategoriesIn(BaseModel):
    categories: list[str]


@router.get("/categories")
def get_categories(user=Depends(current_user)):
    return {"categories": store.get_categories()}


@router.put("/categories")
def put_categories(body: CategoriesIn, user=Depends(current_user)):
    saved = store.set_categories(body.categories)
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


@router.post("/reset")
def reset_db(user=Depends(current_user)):
    """Flush the current user's expense data (demo reset)."""
    deleted = store.delete_user_expenses(user_id=user["id"])
    return {"deleted": deleted}


@router.get("/chart.png")
def chart_png(user=Depends(current_user)):
    docs = store.query_expenses(user_id=user["id"])
    expenses = [e for e in docs if not _is_deposit_doc(e)]
    png = chart.build_pie_chart(expenses)
    return Response(content=png, media_type="image/png")
