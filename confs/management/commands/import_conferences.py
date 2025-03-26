import csv
import datetime as dt
import logging
from pathlib import Path

import requests
from django.core import management
from django_rich.management import RichCommand

from confs.models import Conference


class Command(RichCommand):
    help = "Import instances from a csv file"

    def add_arguments(self, parser):
        parser.add_argument(
            "file_path", nargs="?", default=None, help="Path to the CSV file containing conference data"
        )

    def handle(self, *args, **options):
        file_path = options["file_path"]
        content = ""

        # If no file path provided, download from Google Sheets
        if not file_path:
            self.stdout.write("No file path provided. Downloading file from Google Sheets...")
            url = "https://docs.google.com/spreadsheets/d/1sSfBE01FyJX5h8J9RMm0PaujjcaP4fFqRrmfcRo_dBc/export?exportFormat=csv"

            try:
                response = requests.get(url)
                response.raise_for_status()
                content = response.content.decode("utf-8")
                self.stdout.write("File downloaded successfully")
            except Exception as e:
                self.stderr.write(f"Failed to download file: {e}")
                return
        else:
            # If file path is provided, read from the file
            content = Path(file_path).read_text()

        confs = []
        for line in csv.reader(content.splitlines()[1:]):
            (
                name,
                slug,
                location,
                time_zone,
                start_date,
                end_date,
                posts_after,
                website,
                mastodon,
                description,
                tag,
                imported,
            ) = line
            if not name:
                continue
            if imported.lower() == "yes":
                continue
            conf = Conference(
                name=name,
                slug=slug,
                location=location,
                start_date=dt.datetime.fromisoformat(start_date),
                end_date=dt.datetime.fromisoformat(end_date),
                posts_after=dt.datetime.fromisoformat(posts_after),
                time_zone=time_zone,
                website=website,
                mastodon=mastodon,
                description=description,
                instances="mastodon.social",
                tags=slug if tag in ("", "?") else ",".join(tag.replace(",", " ").split()),
            )
            confs.append(conf)
        if not confs:
            logging.warning("No new conferences found")
            return
        Conference.objects.bulk_create(confs)
        logging.info("Created %s conferences", len(confs))

        management.call_command("findinstances")
        logging.info("Run find instances")

        management.call_command("stattag")
        logging.info("All done! 🎉")
