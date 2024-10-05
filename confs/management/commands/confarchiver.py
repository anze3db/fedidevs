import datetime as dt

from django.utils import timezone
from django_rich.management import RichCommand

from confs.models import Conference


class Command(RichCommand):
    help = "Indexes conferences in the database"

    def handle(self, *args, **options):
        Conference.objects.filter(end_date__lt=timezone.now() - dt.timedelta(days=15)).update(
            archived_date=timezone.now()
        )
        self.console.print("Done archiving 🎉")
