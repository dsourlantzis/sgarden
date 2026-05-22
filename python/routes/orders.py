from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from database import orders_collection, products_collection
from models.order import OrderRequest
from security.jwt_handler import get_current_user

router = APIRouter(prefix="/api/orders", tags=["orders"])

_VALID_TRANSITIONS: dict[str, set] = {
    "pending":   {"confirmed", "cancelled"},
    "confirmed": {"shipped"},
    "shipped":   {"delivered"},
    "delivered": set(),
    "cancelled": set(),
}


def _order_to_response(order: dict) -> dict:
    created = order.get("createdAt")
    updated = order.get("updatedAt")
    return {
        "id": str(order["_id"]),
        "items": order.get("items", []),
        "total": order.get("total", 0),
        "status": order.get("status", "pending"),
        "createdAt": created.isoformat() if created else None,
        "updatedAt": updated.isoformat() if updated else None,
    }


async def _resolve_items(items: list) -> tuple:
    """Fetch product prices, validate stock, compute total."""
    if not items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Validation failed", "errors": {
                "items": "items cannot be empty"
            }},
        )

    resolved = []
    total = 0.0
    stock_updates = []

    for item in items:
        if not ObjectId.is_valid(item.productId):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Validation failed", "errors": {
                    "productId": f"invalid productId: {item.productId}"
                }},
            )

        product = await products_collection.find_one(
            {"_id": ObjectId(item.productId)}
        )
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product not found: {item.productId}",
            )

        available = product.get("stock", 0)
        if item.quantity > available:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Insufficient stock",
                    "errors": {"productId": f"insufficient stock for product: {item.productId}"},
                },
            )

        price = product.get("price", 0)
        total += price * item.quantity
        resolved.append({
            "productId": item.productId,
            "quantity": item.quantity,
            "price": price,
        })
        stock_updates.append((ObjectId(item.productId), item.quantity))

    return resolved, round(total, 2), stock_updates


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_order(
    request: OrderRequest,
    current_user: dict = Depends(get_current_user),
):
    resolved_items, total, stock_updates = await _resolve_items(request.items)

    for product_oid, quantity in stock_updates:
        await products_collection.update_one(
            {"_id": product_oid},
            {"$inc": {"stock": -quantity}, "$set": {"updatedAt": datetime.utcnow()}},
        )

    order_doc = {
        "items": resolved_items,
        "total": total,
        "status": "pending",
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    }

    result = await orders_collection.insert_one(order_doc)
    order_doc["_id"] = result.inserted_id
    return _order_to_response(order_doc)


@router.get("")
async def get_all_orders(
    current_user: dict = Depends(get_current_user),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    query = {}
    if status_filter:
        query["status"] = status_filter
    orders = []
    async for order in orders_collection.find(query):
        orders.append(_order_to_response(order))
    return orders


@router.get("/{order_id}")
async def get_order_by_id(
    order_id: str,
    current_user: dict = Depends(get_current_user),
):
    if not ObjectId.is_valid(order_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    order = await orders_collection.find_one({"_id": ObjectId(order_id)})
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    return _order_to_response(order)


@router.patch("/{order_id}/status")
async def update_order_status(
    order_id: str,
    request: dict,
    current_user: dict = Depends(get_current_user),
):
    if not ObjectId.is_valid(order_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order = await orders_collection.find_one({"_id": ObjectId(order_id)})
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    current_status = order.get("status", "pending")
    new_status = request.get("status")

    if not new_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Validation failed", "errors": {"status": "status is required"}},
        )

    allowed = _VALID_TRANSITIONS.get(current_status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Invalid status transition",
                "errors": {"status": f"cannot transition from '{current_status}' to '{new_status}'"},
            },
        )

    await orders_collection.update_one(
        {"_id": ObjectId(order_id)},
        {"$set": {"status": new_status, "updatedAt": datetime.utcnow()}},
    )

    order = await orders_collection.find_one({"_id": ObjectId(order_id)})
    return _order_to_response(order)


@router.put("/{order_id}")
async def update_order(
    order_id: str,
    request: OrderRequest,
    current_user: dict = Depends(get_current_user),
):
    if not ObjectId.is_valid(order_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    resolved_items, total, _ = await _resolve_items(request.items)

    result = await orders_collection.update_one(
        {"_id": ObjectId(order_id)},
        {"$set": {
            "items": resolved_items,
            "total": total,
            "updatedAt": datetime.utcnow(),
        }},
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    order = await orders_collection.find_one({"_id": ObjectId(order_id)})
    return _order_to_response(order)


@router.delete("/{order_id}")
async def delete_order(
    order_id: str,
    current_user: dict = Depends(get_current_user),
):
    if not ObjectId.is_valid(order_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    result = await orders_collection.delete_one(
        {"_id": ObjectId(order_id)}
    )
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    return {"message": "Order deleted"}
