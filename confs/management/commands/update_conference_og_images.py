import datetime
import logging

from django.utils import timezone
from django_rich.management import RichCommand

from confs.models import Conference
from confs.og_images import get_conference_og_image_signature, render_conference_og_image

logger = logging.getLogger(__name__)


class Command(RichCommand):
    help = "Checks for conference Open Graph images that need to be (re-)rendered and then does so"

    def add_arguments(self, parser):
        parser.add_argument("--stale-after", type=int, nargs="?", default=30)  # days

    def handle(self, *args, stale_after: int = 30, **options):
        start_time = timezone.now()
        date_cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=stale_after)

        # The signature (which reflects the content shown on the card) can't be
        # computed in SQL, so evaluate every conference in Python. This is cheap:
        # there are few conferences and the signature is just a hash of a handful
        # of fields with no I/O.
        conferences = [
            conference
            for conference in Conference.objects.all()
            if conference.og_image_needs_update
            or not conference.og_image
            or get_conference_og_image_signature(conference) != conference.og_image_signature
            or (conference.og_image_updated_at is not None and conference.og_image_updated_at <= date_cutoff)
        ]

        self.console.print(f"Found {len(conferences)} conferences to update.")
        for i, conference in enumerate(conferences):
            self.console.print(
                f"({i + 1}/{len(conferences)}) Rendering OG image for: {conference.name} ({conference.slug})"
            )
            render_conference_og_image(conference)

        self.console.print(
            f"Done. Started at {start_time}. Ended at {timezone.now()}, duration {timezone.now() - start_time}"
        )
