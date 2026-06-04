"""APScheduler cron job that compiles the report every week, in your timezone."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import Application

from .config import CONFIG
from .pipeline import run_scheduled

log = logging.getLogger(__name__)


def build_scheduler(app: Application) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=CONFIG.timezone)
    trigger = CronTrigger(
        day_of_week=CONFIG.report_day,
        hour=CONFIG.report_hour,
        minute=CONFIG.report_minute,
        timezone=CONFIG.timezone,
    )
    scheduler.add_job(
        run_scheduled,
        trigger=trigger,
        args=[app],
        id="weekly_report",
        replace_existing=True,
        misfire_grace_time=3600,  # still run if the host was briefly down
        coalesce=True,
    )
    log.info(
        "Weekly report scheduled for %s at %02d:%02d %s",
        CONFIG.report_day,
        CONFIG.report_hour,
        CONFIG.report_minute,
        CONFIG.timezone,
    )
    return scheduler
