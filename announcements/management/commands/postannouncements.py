import argparse
import logging

from django.conf import settings
from django.utils import timezone
from django_rich.management import RichCommand
from mastodon import Mastodon

from announcements.models import Announcement

logger = logging.getLogger(__name__)


class Command(RichCommand):
    help = "Posts any due announcements to the @fedidevs fediverse account"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action=argparse.BooleanOptionalAction,
            default=True,
            help="Preview the announcements without posting them (default). Pass --no-dry-run to actually post.",
        )

    def handle(self, *args, dry_run=True, **options):
        due = list(Announcement.objects.filter(posted_at__isnull=True, post_at__lte=timezone.now()))
        if not due:
            self.console.print("Nothing to announce 🎉")
            return

        if dry_run:
            for announcement in due:
                self.console.print(f"[cyan]{announcement}:[/cyan]\n{announcement.content}\n")
            self.console.print(
                f"[yellow]Dry run: {len(due)} announcement(s) not posted. "
                "Run with `./manage.py postannouncements --no-dry-run` to actually post.[/yellow]"
            )
            return

        if not settings.FEDIDEVS_BOT_ACCESS_TOKEN:
            self.console.print("[yellow]FEDIDEVS_BOT_ACCESS_TOKEN not set, skipping announcements[/yellow]")
            return

        mastodon = None
        for announcement in due:
            if mastodon is None:
                mastodon = Mastodon(
                    access_token=settings.FEDIDEVS_BOT_ACCESS_TOKEN,
                    api_base_url=settings.FEDIDEVS_BOT_API_BASE_URL,
                )

            try:
                status = mastodon.status_post(announcement.content, visibility=announcement.visibility)
            except Exception as exc:
                logger.exception("Failed to post announcement %s", announcement.pk)
                announcement.error = str(exc)
                announcement.save(update_fields=["error"])
                self.console.print(f"[red]Failed to post {announcement}: {exc}[/red]")
                continue

            announcement.posted_at = timezone.now()
            announcement.post_url = status["url"]
            announcement.error = ""
            announcement.save(update_fields=["posted_at", "post_url", "error"])
            self.console.print(f"Posted {announcement} → {announcement.post_url}")

        self.console.print("Done announcing 🎉")
