from django.utils import timezone
from django_rich.management import RichCommand

from announcements.models import Announcement
from confs.conference_announcements import sync_upcoming
from confs.models import Conference


class Command(RichCommand):
    help = "Prepares start/end announcements for all upcoming conferences"

    def handle(self, *args, **options):
        sync_upcoming(Conference, Announcement, timezone.now().date())
        self.console.print("Done syncing announcements 🎉")
