"""Computes the four dashboard views from the current SKU snapshot +
recent sales history. Deliberately simple, documented heuristics for
v1 - not "AI-powered forecasting" (nobody has validated that's needed
yet, and a simple, explainable number a retailer can sanity-check beats
an opaque one they can't)."""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import SKU, SaleRecord

TOP_SELLER_COUNT = 15
STALE_DAYS = 30


def compute_dashboard(db: Session, user_id: int) -> dict:
    today = date.today()
    week_ago = today - timedelta(days=7)
    stale_cutoff = today - timedelta(days=STALE_DAYS)

    recent_sales = (
        db.query(SaleRecord)
        .filter(SaleRecord.user_id == user_id, SaleRecord.date >= week_ago)
        .all()
    )
    weekly = {}
    for s in recent_sales:
        agg = weekly.setdefault(s.sku_code, {"qty": 0.0, "revenue": 0.0})
        agg["qty"] += s.quantity
        agg["revenue"] += s.revenue

    top_sellers = sorted(
        ({"sku": sku, **vals} for sku, vals in weekly.items()),
        key=lambda x: -x["revenue"],
    )[:TOP_SELLER_COUNT]

    skus = db.query(SKU).filter(SKU.user_id == user_id).all()

    reorder_alerts = sorted(
        [s for s in skus if s.on_hand <= s.reorder_point],
        key=lambda s: s.on_hand - s.reorder_point,
    )

    stale_stock = [
        s for s in skus
        if s.last_sale_date is None or s.last_sale_date <= stale_cutoff
    ]

    suggested_orders = []
    for s in skus:
        weekly_qty = weekly.get(s.sku_code, {"qty": 0.0})["qty"]
        safety_stock = weekly_qty * 0.5  # half a week of recent sales as buffer
        suggested_qty = (s.reorder_point + safety_stock) - s.on_hand
        if suggested_qty > 0:
            suggested_orders.append({
                "sku": s.sku_code, "name": s.name,
                "suggested_qty": round(suggested_qty),
                "on_hand": s.on_hand, "reorder_point": s.reorder_point,
            })
    suggested_orders.sort(key=lambda x: -x["suggested_qty"])

    return {
        "top_sellers": top_sellers,
        "reorder_alerts": reorder_alerts,
        "stale_stock": stale_stock,
        "suggested_orders": suggested_orders,
        "has_data": bool(skus),
        "generated_at": today,
    }
