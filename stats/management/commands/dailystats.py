from django_rich.management import RichCommand

from stats.models import store_daily_stats


class Command(RichCommand):
    help = "Gather daily stats"

    def handle(self, *args, **options):
        self.console.print("Gathering daily stats")
        store_daily_stats()
