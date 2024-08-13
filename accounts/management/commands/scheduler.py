import time

import schedule
from django.core import management
from django_rich.management import RichCommand


class Command(RichCommand):
    help = "Starts the scheduler"

    def daily_job(self):
        self.console.print("Starting daily job")
        self.console.print("Running crawler")
        management.call_command("crawler", skip_inactive_for=3, pre_filter=True)
        self.console.print("Running indexer")
        management.call_command("indexer")
        # TODO: Optimizer should no longer be needed because crawler is pre-filtering
        # self.console.print("Running optimizer")
        # management.call_command("optimizer")
        self.console.print("Running statuser")
        management.call_command("statuser")
        self.console.print("Running findinstances")
        management.call_command("findinstances")
        self.console.print("Running stattag")
        management.call_command("stattag")
        self.console.print("Running classify")
        management.call_command("classify")
        self.console.print("Running stats")
        management.call_command("dailystats")
        management.call_command("dailyaccountstats")
        self.console.print("All done! 🎉")

    def hourly_job(self):
        self.console.print("Starting hourly job")
        management.call_command("stattag", "--active")
        self.console.print("All done! 🎉")

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
            self.hourly_job()
            self.daily_job()
            return

        self.console.print("Starting scheduler 🕐")
        schedule.every().day.at("01:00").do(self.daily_job)
        schedule.every().hour.do(self.hourly_job)

        while True:
            schedule.run_pending()
            time.sleep(1)
