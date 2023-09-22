import time

import schedule
from django.core import management
from django_rich.management import RichCommand
from sentry_sdk.crons import monitor


class Command(RichCommand):
    help = "Starts the scheduler"

    @monitor(monitor_slug="daily-sync")
    def job(self):
        self.console.print("Starting daily job")
        self.console.print("Running crawler")
        with monitor(monitor_slug="daily-sync-crawler"):
            management.call_command("crawler", skip_inactive_for=3, pre_filter=True)
        self.console.print("Running indexer")
        with monitor(monitor_slug="daily-sync-indexer"):
            management.call_command("indexer")
        self.console.print("Running optimizer")
        with monitor(monitor_slug="daily-sync-optimizer"):
            management.call_command("optimizer")
        self.console.print("Running statuser")
        with monitor(monitor_slug="daily-sync-statuser"):
            management.call_command("statuser")
        self.console.print("Running dailystats")
        with monitor(monitor_slug="daily-sync-stats"):
            management.call_command("dailystats")
        self.console.print("All done! 🎉")

    def handle(self, *args, **options):
        self.console.print("Starting scheduler 🕐")
        schedule.every().day.at("01:00").do(self.job)

        while True:
            schedule.run_pending()
            time.sleep(1)
