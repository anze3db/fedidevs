import csv
import datetime as dt
import logging
from pathlib import Path

from django.core import management
from django.template.defaultfilters import slugify
from django.utils import timezone
from django_rich.management import RichCommand

from confs.models import Conference


class Command(RichCommand):
    help = "Import instances from a csv file"

    def handle(self, *args, **options):
        confs = []
        for i, line in enumerate(csv.reader(Path("instances.csv").read_text().splitlines())):
            if i < 4:
                continue

            name, location, start_date, end_date, website, mastodon, description, tag, imported = line
            if imported == "yes":
                continue
            slug = slugify(name.replace(" ", "").replace("20", ""))
            conf = Conference(
                name=name,
                slug=slug,
                location=location,
                start_date=dt.datetime.fromisoformat(start_date),
                end_date=dt.datetime.fromisoformat(end_date),
                website=website,
                mastodon=mastodon,
                description=description,
                posts_after=timezone.now().date().replace(month=1, day=1),
                instances="mastodon.social",
                tags=slug if tag in ("", "?") else tag,
            )
            confs.append(conf)
        if not confs:
            logging.warning("No new conferences found")
            return
        Conference.objects.bulk_create(confs)
        logging.info("Created %s conferences", len(confs))

        management.call_command("findinstances")
        logging.info("Rand find instances")

        management.call_command("stattag")
        logging.info("All done! 🎉")
