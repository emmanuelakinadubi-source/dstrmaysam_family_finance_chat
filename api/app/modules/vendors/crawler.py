import logging
from datetime import datetime, timezone
from typing import List, Dict

logger = logging.getLogger(__name__)

SAMPLE_GROCERY_DATA: List[Dict] = [
    {"vendor_name": "Tesco", "product_name": "Whole Milk 6 pints", "price": 1.89, "category": "Dairy", "vendor_type": "grocery"},
    {"vendor_name": "Aldi", "product_name": "Whole Milk 6 pints", "price": 1.49, "category": "Dairy", "vendor_type": "grocery"},
    {"vendor_name": "Lidl", "product_name": "Whole Milk 6 pints", "price": 1.55, "category": "Dairy", "vendor_type": "grocery"},
    {"vendor_name": "Asda", "product_name": "Whole Milk 6 pints", "price": 1.75, "category": "Dairy", "vendor_type": "grocery"},
    {"vendor_name": "Morrisons", "product_name": "Whole Milk 6 pints", "price": 1.80, "category": "Dairy", "vendor_type": "grocery"},
    {"vendor_name": "Sainsbury's", "product_name": "Whole Milk 6 pints", "price": 1.85, "category": "Dairy", "vendor_type": "grocery"},
    {"vendor_name": "Tesco", "product_name": "Chicken Breast 1kg", "price": 5.50, "category": "Meat", "vendor_type": "grocery"},
    {"vendor_name": "Aldi", "product_name": "Chicken Breast 1kg", "price": 4.29, "category": "Meat", "vendor_type": "grocery"},
    {"vendor_name": "Lidl", "product_name": "Chicken Breast 1kg", "price": 4.49, "category": "Meat", "vendor_type": "grocery"},
    {"vendor_name": "Asda", "product_name": "Chicken Breast 1kg", "price": 4.99, "category": "Meat", "vendor_type": "grocery"},
]


def run_crawl() -> int:
    """Seed/refresh vendor price data. Returns the number of records upserted."""
    try:
        from app.core.database import SessionLocal
        from app.models.vendor import VendorPrice

        db = SessionLocal()
        count = 0
        for item in SAMPLE_GROCERY_DATA:
            record = VendorPrice(
                **item,
                currency="GBP",
                source_url="https://sample-crawl.local",
                crawled_at=datetime.now(timezone.utc),
            )
            db.add(record)
            count += 1
        db.commit()
        db.close()
        logger.info("Vendor crawl complete — %d records inserted", count)
        return count
    except Exception as e:
        logger.error("Crawl error: %s", e)
        return 0
