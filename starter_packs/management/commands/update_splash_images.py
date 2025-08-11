import datetime
import logging
import time

from django.db.models import Q
from django.utils import timezone
from django_rich.management import RichCommand

from starter_packs.models import StarterPack
from starter_packs.splash_images import render_splash_image

logger = logging.getLogger(__name__)


class Command(RichCommand):
    help = "Checks for starter pack splash images that need to be (re-)rendered and then does so"

    def add_arguments(self, parser):
        parser.add_argument("--stale-after", type=int, nargs="?", default=14)  # days
        parser.add_argument("--seconds-between", type=int, nargs="?", default=2)
        parser.add_argument("--host-attribution", type=str, nargs="?", default="fedidevs.com")

    def handle(
        self,
        *args,
        stale_after: int = 30,
        seconds_between: int = 2,
        host_attribution: str = "fedidevs.com",
        **options,
    ):
        self.main(
            stale_after=stale_after,
            seconds_between=seconds_between,
            host_attribution=host_attribution,
        )

    def main(
        self,
        stale_after: int = 30,
        seconds_between: int = 2,
        host_attribution: str = "",
    ):
        # This command works synchronously and in a single thread in order to avoid
        # multiple concurrent HTTP requests for avatar files. (Trying to be somewhat
        # polite to remote servers.)
        self.run_once(stale_after, seconds_between, host_attribution)

    def run_once(self, stale_after, seconds_between, host_attribution):
        self.console.print("Checking which starter packs need to have their splash images rerendered.")
        start_time = timezone.now()
        date_cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=stale_after)

        starter_packs = StarterPack.objects.filter(published_at__isnull=False).filter(
            Q(splash_image="") | Q(splash_image_needs_update=True) | Q(splash_image_updated_at__lte=date_cutoff)
        )

        self.console.print(f"Found {len(starter_packs)} starter packs to update.")
        self.render_splash_images_for(starter_packs, host_attribution, seconds_between)

        self.console.print(
            f"Done. Started at {start_time}. Ended at {timezone.now()}, duration {timezone.now() - start_time}"
        )

    def render_splash_images_for(self, starter_packs, host_attribution, seconds_between):
        for i in range(len(starter_packs)):
            self.console.print(
                f"({i + 1}/{len(starter_packs)}) Rendering splash image for: {starter_packs[i].title} ({starter_packs[i].slug})"
            )
            render_splash_image(starter_packs[i], host_attribution)
            time.sleep(seconds_between)
