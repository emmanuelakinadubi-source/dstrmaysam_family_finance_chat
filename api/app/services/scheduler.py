import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler()


async def _daily_indexing_job() -> None:
    from app.services.indexing_service import run_incremental_indexing
    logger.info("Scheduled daily venue indexing started")
    try:
        result = run_incremental_indexing()
        logger.info("Scheduled indexing complete: %s", result)
    except Exception as exc:
        logger.error("Scheduled indexing failed: %s", exc)


def start_scheduler() -> None:
    _scheduler.add_job(
        _daily_indexing_job,
        CronTrigger(hour=4, minute=0),
        id="daily_venue_indexing",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    logger.info("Scheduler started — daily venue indexing at 04:00 UTC")


def shutdown_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")


def get_next_run_time() -> str:
    job = _scheduler.get_job("daily_venue_indexing")
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return "unknown"
