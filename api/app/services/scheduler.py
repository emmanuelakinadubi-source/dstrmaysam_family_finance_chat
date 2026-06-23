import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler()


# ── Jobs ───────────────────────────────────────────────────────────────────────

async def _daily_venue_indexing_job() -> None:
    from app.services.indexing_service import run_incremental_indexing
    logger.info("Scheduled daily venue indexing started")
    try:
        result = run_incremental_indexing()
        logger.info("Scheduled venue indexing complete: %s", result)
    except Exception as exc:
        logger.error("Scheduled venue indexing failed: %s", exc)


def _weekly_vendor_crawl_job() -> None:
    from app.modules.vendors.crawler import run_crawl
    logger.info("Scheduled weekly vendor crawl started")
    try:
        result = run_crawl()
        logger.info("Scheduled vendor crawl complete: %s", result)
    except Exception as exc:
        logger.error("Scheduled vendor crawl failed: %s", exc)


# ── Lifecycle ──────────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    # Daily venue indexing — 04:00 UTC
    _scheduler.add_job(
        _daily_venue_indexing_job,
        CronTrigger(hour=4, minute=0),
        id="daily_venue_indexing",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Weekly vendor + hotel crawl — Sundays 02:00 UTC
    _scheduler.add_job(
        _weekly_vendor_crawl_job,
        CronTrigger(day_of_week="sun", hour=2, minute=0),
        id="weekly_vendor_crawl",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    _scheduler.start()
    logger.info(
        "Scheduler started — venue indexing daily at 04:00 UTC, "
        "vendor crawl weekly on Sundays at 02:00 UTC"
    )


def shutdown_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")


def get_next_run_time(job_id: str = "daily_venue_indexing") -> str:
    job = _scheduler.get_job(job_id)
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return "unknown"
