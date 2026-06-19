import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.core.config import settings

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def crawl_vendor_prices() -> None:
    logger.info("Starting scheduled vendor price crawl")
    try:
        from app.modules.vendors.crawler import run_crawl
        run_crawl()
    except Exception as e:
        logger.error(f"Vendor crawl failed: {e}")


def start_scheduler() -> None:
    scheduler.add_job(
        crawl_vendor_prices,
        trigger=CronTrigger(
            hour=settings.vendor_crawl_hour,
            minute=settings.vendor_crawl_minute,
        ),
        id="vendor_price_crawl",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started — vendor crawl at %02d:%02d daily",
                settings.vendor_crawl_hour, settings.vendor_crawl_minute)


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
