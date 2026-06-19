from __future__ import annotations
import uuid
from typing import Optional, List
from pydantic import BaseModel


class VendorPriceOut(BaseModel):
    id: uuid.UUID
    vendor_name: str
    product_name: str
    price: float
    currency: str
    category: str
    vendor_type: str
    source_url: Optional[str]

    class Config:
        from_attributes = True


class VendorCompareRequest(BaseModel):
    vendor_names: List[str]
    category: Optional[str] = None


class VendorMatchRequest(BaseModel):
    budget: float
    attendee_count: int
    food_requirements: Optional[str] = None
    location: Optional[str] = None
    vendor_type: str = "catering"
