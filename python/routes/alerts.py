from fastapi import APIRouter, Depends, HTTPException, status

from database import products_collection, settings_collection
from security.jwt_handler import get_current_user

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

_DEFAULT_THRESHOLD = 10
_THRESHOLD_KEY = "alert_threshold"


def _severity(stock: int, threshold: int) -> str:
    if stock <= threshold * 0.25:
        return "critical"
    if stock <= threshold * 0.5:
        return "warning"
    return "info"


async def _get_threshold() -> int:
    doc = await settings_collection.find_one({"key": _THRESHOLD_KEY})
    return doc["value"] if doc else _DEFAULT_THRESHOLD


@router.get("")
async def get_alerts(current_user: dict = Depends(get_current_user)):
    threshold = await _get_threshold()
    alerts = []
    async for product in products_collection.find({"stock": {"$lt": threshold}}):
        stock = product.get("stock", 0)
        alerts.append({
            "productId": str(product["_id"]),
            "productName": product.get("name"),
            "stock": stock,
            "threshold": threshold,
            "severity": _severity(stock, threshold),
        })
    return alerts


@router.put("/threshold")
async def set_threshold(request: dict, current_user: dict = Depends(get_current_user)):
    threshold = request.get("threshold")
    if threshold is None or not isinstance(threshold, (int, float)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Validation failed", "errors": {"threshold": "threshold is required"}},
        )
    if threshold < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Validation failed", "errors": {"threshold": "threshold cannot be negative"}},
        )

    threshold = int(threshold)
    await settings_collection.update_one(
        {"key": _THRESHOLD_KEY},
        {"$set": {"key": _THRESHOLD_KEY, "value": threshold}},
        upsert=True,
    )
    return {"threshold": threshold}
