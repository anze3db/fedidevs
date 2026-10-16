"""Periodic jobs, scheduled through POTATOQ_BEAT_SCHEDULE in settings."""

import logging

from django.core import management
from potatoq import shared_task

from mastodon_auth.models import Instance

logger = logging.getLogger(__name__)


# The nightly crawl runs for hours, well past potatoq's default 30 minute limit.
@shared_task(time_limit=None)
def daily_job():
    logger.info("Starting daily job")
    if not Instance.objects.exists():
        logger.info("Running instances")
        management.call_command("instances")
    logger.info("Running crawler")
    management.call_command("crawler", skip_inactive_for=3)
    logger.info("Running indexer")
    management.call_command("indexer")
    logger.info("Running findinstances")
    management.call_command("findinstances")
    logger.info("Running stattag")
    management.call_command("stattag")
    logger.info("Running classify")
    management.call_command("classify")
    logger.info("Running stats")
    management.call_command("dailystats")
    management.call_command("dailypackstats")
    management.call_command("dailyaccountstats")
    logger.info("Archiving conferences")
    management.call_command("confarchiver")
    logger.info("Syncing conference announcements")
    management.call_command("syncannouncements")
    logger.info("Updating splash images")
    management.call_command("update_splash_images")
    logger.info("Updating conference OG images")
    management.call_command("update_conference_og_images")
    logger.info("Daily job done")


@shared_task
def hourly_job():
    logger.info("Starting hourly job")
    management.call_command("stattag", "--active")
    logger.info("Posting due announcements")
    management.call_command("postannouncements", "--no-dry-run")
    logger.info("Hourly job done")
