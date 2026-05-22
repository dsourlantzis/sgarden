from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class OrderItem(BaseModel):
    productId: str
    quantity: int = Field(..., ge=1)


class OrderRequest(BaseModel):
    items: List[OrderItem]


class OrderItemResponse(BaseModel):
    productId: str
    quantity: int
    price: float


class OrderInDB(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    items: List[OrderItemResponse]
    total: float
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class OrderResponse(BaseModel):
    id: str
    items: List[OrderItemResponse]
    total: float
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None
