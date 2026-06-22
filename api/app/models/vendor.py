from sqlalchemy import Column, String, Float, DateTime, Boolean
from sqlalchemy.sql import func
from app.db.base import UUIDBase


class Vendor(UUIDBase):
    """Simple vendor table for MVP event matching."""
    __tablename__ = "vendors"

    vendor_name = Column(String(150), nullable=False, index=True)
    vendor_type = Column(String(50), nullable=False, index=True)  # Catering | Hotel | Conference
    city = Column(String(100), nullable=False, index=True)
    price_per_person = Column(Float, nullable=False)
    currency = Column(String(10), default="GBP", nullable=False)
    description = Column(String(300), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)


class VendorPrice(UUIDBase):
    """Detailed price catalog — populated by crawler (Phase 2)."""
    __tablename__ = "vendor_prices"

    vendor_name = Column(String(150), nullable=False, index=True)
    product_name = Column(String(200), nullable=False)
    price = Column(Float, nullable=False)
    currency = Column(String(10), default="GBP", nullable=False)
    category = Column(String(100), nullable=False, index=True)
    vendor_type = Column(String(50), nullable=False, index=True)
    source_url = Column(String(500), nullable=True)
    crawled_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
