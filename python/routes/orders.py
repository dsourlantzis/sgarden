from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from database import orders_collection, products_collection
from models.order import OrderRequest
from security.jwt_handler import get_current_user

router = APIRouter(prefix="/api/orders", tags=["orders"])


def _order_to_response(order: dict) -> dict:
    created = order.get("createdAt")
    updated = order.get("updatedAt")
    return {
        "id": str(order["_id"]),
        "items": order.get("items", []),
        "total": order.get("total", 0),
        "createdAt": created.isoformat() if created else None,
        "updatedAt": updated.isoformat() if updated else None,
    }


async def _resolve_items(items: list) -> tuple:
    """Fetch product prices and compute total."""
    if not items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Validation failed", "errors": {
                "items": "items cannot be empty"
            }},
        )

    resolved = []
    total = 0.0

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

        price = product.get("price", 0)
        total += price * item.quantity
        resolved.append({
            "productId": item.productId,
            "quantity": item.quantity,
            "price": price,
        })

    return resolved, round(total, 2)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_order(
    request: OrderRequest,
    current_user: dict = Depends(get_current_user),
):
    resolved_items, total = await _resolve_items(request.items)

    order_doc = {
        "items": resolved_items,
        "total": total,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    }

    result = await orders_collection.insert_one(order_doc)
    order_doc["_id"] = result.inserted_id
    return _order_to_response(order_doc)


@router.get("")
async def get_all_orders(
    current_user: dict = Depends(get_current_user),
):
    orders = []
    async for order in orders_collection.find():
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

    resolved_items, total = await _resolve_items(request.items)

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
