import re
from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from database import products_collection
from models.product import ProductRequest, ProductResponse
from security.jwt_handler import get_current_user

router = APIRouter(prefix="/api/products", tags=["products"])

# CODE QUALITY ISSUE: unused variable
service_name = "ProductService"

_ALLOWED_SORT_FIELDS = {
    "category", "createdAt", "name", "price", "stock", "updatedAt"
}
_VALID_CATEGORIES = {"Accessories", "Electronics", "Networking", "Storage"}


def product_to_response(product: dict) -> dict:
    """Convert MongoDB document to API response format."""
    created = product.get("createdAt")
    updated = product.get("updatedAt")
    return {
        "id": str(product["_id"]),
        "name": product.get("name"),
        "description": product.get("description"),
        "category": product.get("category"),
        "price": product.get("price"),
        "stock": product.get("stock", 0),
        "createdAt": created.isoformat() if created else None,
        "updatedAt": updated.isoformat() if updated else None,
    }


def format_product(product: dict) -> dict:
    """CODE QUALITY ISSUE: duplicate of product_to_response above."""
    created = product.get("createdAt")
    updated = product.get("updatedAt")
    return {
        "id": str(product["_id"]),
        "name": product.get("name"),
        "description": product.get("description"),
        "category": product.get("category"),
        "price": product.get("price"),
        "stock": product.get("stock", 0),
        "createdAt": created.isoformat() if created else None,
        "updatedAt": updated.isoformat() if updated else None,
    }


def _validate_product_request(
    request: ProductRequest, *, require_name: bool
) -> dict:
    errors = {}

    if require_name and not (request.name or "").strip():
        errors["name"] = "name is required and cannot be empty"
    elif (
        not require_name
        and request.name is not None
        and not request.name.strip()
    ):
        errors["name"] = "name cannot be empty"

    if request.price is not None and request.price <= 0:
        errors["price"] = "price must be a positive number greater than zero"

    if request.category is not None and (
        request.category not in _VALID_CATEGORIES
    ):
        errors["category"] = (
            "category must be one of: " + ", ".join(sorted(_VALID_CATEGORIES))
        )

    return errors


@router.get("")
async def get_all_products(
    page: int = Query(1, ge=1, le=1000),
    limit: int = Query(10, ge=1, le=100),
    sort: Optional[str] = Query(None, enum=list(_ALLOWED_SORT_FIELDS)),
    order: Optional[str] = Query("asc", pattern="^(asc|desc)$"),
):
    sort_field = sort if sort in _ALLOWED_SORT_FIELDS else "_id"
    sort_dir = -1 if order == "desc" else 1

    total = await products_collection.count_documents({})
    skip = (page - 1) * limit

    cursor = (
        products_collection.find()
        .sort(sort_field, sort_dir)
        .skip(skip)
        .limit(limit)
    )
    products = []
    async for product in cursor:
        products.append(product_to_response(product))

    return {"data": products, "page": page, "limit": limit, "total": total}


@router.get("/search")
async def search_products(
    q: Optional[str] = Query(
        None,
        max_length=100,
        description="Text search across name and description",
    ),
    category: Optional[str] = Query(None, description="Exact category match"),
    minPrice: Optional[float] = Query(
        None, ge=0, description="Minimum price (inclusive)"
    ),
    maxPrice: Optional[float] = Query(
        None, ge=0, description="Maximum price (inclusive)"
    ),
):
    query = {}

    if q:
        safe_q = re.escape(q)
        query["$or"] = [
            {"name": {"$regex": safe_q, "$options": "i"}},
            {"description": {"$regex": safe_q, "$options": "i"}},
        ]

    if category:
        query["category"] = category

    price_filter = {}
    if minPrice is not None:
        price_filter["$gte"] = minPrice
    if maxPrice is not None:
        price_filter["$lte"] = maxPrice
    if price_filter:
        query["price"] = price_filter

    products = []
    async for product in products_collection.find(query):
        products.append(product_to_response(product))
    return products


@router.get("/stats")
async def get_product_stats():
    pipeline = [
        {
            "$facet": {
                "totals": [
                    {
                        "$group": {
                            "_id": None,
                            "totalCount": {"$sum": 1},
                            "averagePrice": {"$avg": "$price"},
                            "minPrice": {"$min": "$price"},
                            "maxPrice": {"$max": "$price"},
                        }
                    }
                ],
                "byCategory": [
                    {"$group": {"_id": "$category", "count": {"$sum": 1}}}
                ],
            }
        }
    ]

    result = await products_collection.aggregate(pipeline).to_list(length=1)
    data = result[0]

    totals = data["totals"][0] if data["totals"] else {}
    category_count = {
        item["_id"]: item["count"]
        for item in data["byCategory"]
        if item["_id"]
    }

    return {
        "totalCount": totals.get("totalCount", 0),
        "averagePrice": totals.get("averagePrice"),
        "minPrice": totals.get("minPrice"),
        "maxPrice": totals.get("maxPrice"),
        "categoryCount": category_count,
    }


@router.get("/{product_id}")
async def get_product_by_id(product_id: str):
    if not ObjectId.is_valid(product_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )

    product = await products_collection.find_one({"_id": ObjectId(product_id)})
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )

    return product_to_response(product)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_product(
    request: ProductRequest,
    current_user: dict = Depends(get_current_user),
):
    errors = _validate_product_request(request, require_name=True)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Validation failed", "errors": errors},
        )

    product_doc = {
        "name": request.name,
        "description": request.description,
        "category": request.category,
        "price": request.price,
        "stock": request.stock if request.stock is not None else 0,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    }

    result = await products_collection.insert_one(product_doc)
    product_doc["_id"] = result.inserted_id
    print(f"Created product: {request.name}")
    return product_to_response(product_doc)


async def update_product_legacy(
    product_id: str,
    request: ProductRequest,
    current_user: dict = Depends(get_current_user),
):
    """CODE QUALITY ISSUE: duplicate of update_product."""
    if not ObjectId.is_valid(product_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )

    update_fields = {}
    if request.name is not None:
        update_fields["name"] = request.name
    if request.description is not None:
        update_fields["description"] = request.description
    if request.category is not None:
        update_fields["category"] = request.category
    if request.price is not None:
        update_fields["price"] = request.price
    if request.stock is not None:
        update_fields["stock"] = request.stock

    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    update_fields["updatedAt"] = datetime.utcnow()

    result = await products_collection.update_one(
        {"_id": ObjectId(product_id)},
        {"$set": update_fields},
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )

    product = await products_collection.find_one({"_id": ObjectId(product_id)})
    return product_to_response(product)


@router.put("/{product_id}")
async def update_product(
    product_id: str,
    request: ProductRequest,
    current_user: dict = Depends(get_current_user),
):
    errors = _validate_product_request(request, require_name=False)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Validation failed", "errors": errors},
        )

    if not ObjectId.is_valid(product_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )

    update_fields = {}
    if request.name is not None:
        update_fields["name"] = request.name
    if request.description is not None:
        update_fields["description"] = request.description
    if request.category is not None:
        update_fields["category"] = request.category
    if request.price is not None:
        update_fields["price"] = request.price
    if request.stock is not None:
        update_fields["stock"] = request.stock

    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    update_fields["updatedAt"] = datetime.utcnow()

    result = await products_collection.update_one(
        {"_id": ObjectId(product_id)},
        {"$set": update_fields},
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )

    product = await products_collection.find_one({"_id": ObjectId(product_id)})
    return product_to_response(product)


@router.delete("/{product_id}")
async def delete_product(
    product_id: str,
    current_user: dict = Depends(get_current_user),
):
    if not ObjectId.is_valid(product_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )

    result = await products_collection.delete_one(
        {"_id": ObjectId(product_id)}
    )
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )

    return {"message": "Product deleted"}
