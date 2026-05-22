from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from database import orders_collection, products_collection
from security.jwt_handler import get_current_user

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/sales")
async def get_sales_analytics(
    current_user: dict = Depends(get_current_user),
    startDate: Optional[str] = Query(None),
    endDate: Optional[str] = Query(None),
):
    date_filter = {}
    try:
        if startDate:
            date_filter["$gte"] = datetime.fromisoformat(startDate)
        if endDate:
            date_filter["$lte"] = datetime.fromisoformat(endDate + "T23:59:59.999999")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Validation failed", "errors": {"date": "invalid date format, use YYYY-MM-DD"}},
        )

    match = {"createdAt": date_filter} if date_filter else {}

    # Totals + revenueByPeriod in one round-trip
    summary_pipeline = [
        {"$match": match},
        {
            "$facet": {
                "totals": [
                    {"$group": {
                        "_id": None,
                        "totalRevenue": {"$sum": "$total"},
                        "totalOrders": {"$sum": 1},
                    }}
                ],
                "byPeriod": [
                    {"$group": {
                        "_id": {"$dateToString": {"format": "%Y-%m", "date": "$createdAt"}},
                        "revenue": {"$sum": "$total"},
                        "orders": {"$sum": 1},
                    }},
                    {"$sort": {"_id": 1}},
                ],
            }
        },
    ]

    summary_result = await orders_collection.aggregate(summary_pipeline).to_list(length=1)
    data = summary_result[0] if summary_result else {}

    totals = data.get("totals", [])
    total_revenue = round(totals[0].get("totalRevenue", 0), 2) if totals else 0
    total_orders = totals[0].get("totalOrders", 0) if totals else 0

    revenue_by_period = [
        {"period": item["_id"], "revenue": round(item["revenue"], 2), "orders": item["orders"]}
        for item in data.get("byPeriod", [])
        if item.get("_id")
    ]

    # Top products — unwind, group, then $lookup product names in one pipeline
    top_pipeline = [
        {"$match": match},
        {"$unwind": "$items"},
        {"$group": {
            "_id": "$items.productId",
            "totalQuantity": {"$sum": "$items.quantity"},
            "totalRevenue": {"$sum": {"$multiply": ["$items.price", "$items.quantity"]}},
        }},
        {"$sort": {"totalRevenue": -1}},
        {"$limit": 10},
        {"$addFields": {
            "productOid": {
                "$convert": {"input": "$_id", "to": "objectId", "onError": None, "onNull": None}
            }
        }},
        {"$lookup": {
            "from": "products",
            "localField": "productOid",
            "foreignField": "_id",
            "as": "productInfo",
        }},
        {"$project": {
            "totalQuantity": 1,
            "totalRevenue": 1,
            "productName": {"$arrayElemAt": ["$productInfo.name", 0]},
        }},
    ]

    top_raw = await orders_collection.aggregate(top_pipeline).to_list(length=10)

    top_products = [
        {
            "productId": item["_id"],
            "productName": item.get("productName"),
            "totalQuantity": item["totalQuantity"],
            "totalRevenue": round(item["totalRevenue"], 2),
        }
        for item in top_raw
    ]

    return {
        "totalRevenue": total_revenue,
        "totalOrders": total_orders,
        "topProducts": top_products,
        "revenueByPeriod": revenue_by_period,
    }
