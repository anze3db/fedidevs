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
        # TODO: Optimizer should no longer be needed because crawler is pre-filtering
        self.console.print("Running optimizer")
        with monitor(monitor_slug="daily-sync-optimizer"):
            pass  # Enabling the monitor just to test out if the Sentry issue was resolved
        #     management.call_command("optimizer")
        self.console.print("Running statuser")
        with monitor(monitor_slug="daily-sync-statuser"):
            management.call_command("statuser")
        self.console.print("Running dailystats")
        with monitor(monitor_slug="daily-sync-stats"):
            management.call_command("dailystats")
        self.console.print("All done! 🎉")

    def djangocon_job(self):
        self.console.print("Running djangocon job")
        management.call_command("stattag")
        self.console.print("Finished djangocon job")

    def fwd50_job(self):
        self.console.print("Running fwd50 job")
        management.call_command(
            "stattag",
            tags="fwd50",
            instances="mastodon.social,mastodon.sboots.ca,mastodon.me.uk,mstdn.ca,cosocial.ca",
        )
        self.console.print("Finished fwd50 job")

    def djangoconafrica_job(self):
        self.console.print("Running djangoconafrica job")
        management.call_command(
            "stattag",
            tags="djangoconafrica",
            instances="fosstodon.org,mastodon.social",
        )
        self.console.print("Finished djangoconafrica job")

    def dotnetconf_job(self):
        self.console.print("Running dotnetconf job")
        management.call_command(
            "stattag",
            tags="dotnetconf",
            instances="fosstodon.org,mastodon.social,indieweb.social,toot.community,dotnet.social",
        )
        self.console.print("Finished dotnetconf job")

    def add_arguments(self, parser):
        parser.add_argument("--offset", type=int, nargs="?", default=0)
        parser.add_argument("--instances", type=str, nargs="?", default=None)
        parser.add_argument("--skip-inactive-for", type=int, nargs="?", default=90)
        parser.add_argument(
            "--run-now",
            action="store_true",
            help="Run the scheduled job(s) once and then exit",
        )

    def handle(self, *args, run_now=False, **options):
        if run_now:
            self.console.print("Running job(s) now 🏃‍♂️")
            # self.djangoconafrica_job()
            # self.fwd50_job()
            # self.dotnetconf_job()
            self.job()
            return

        self.console.print("Starting scheduler 🕐")
        schedule.every().day.at("01:00").do(self.job)
        # schedule.every().day.at("00:00").do(self.fwd50_job)
        # schedule.every(30).minutes.do(self.djangoconafrica_job)
        # schedule.every(30).minutes.do(self.dotnetconf_job)

        while True:
            schedule.run_pending()
            time.sleep(1)
