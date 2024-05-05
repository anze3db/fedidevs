from django.db.models import Q
from django_rich.management import RichCommand

from confs.models import FRAMEWORKS, LANGUAGES, Conference, ConferenceLookup


class Command(RichCommand):
    help = "Indexes conferences in the database"

    def handle(self, *args, **options):
        for lang in LANGUAGES + FRAMEWORKS:
            self.console.print(f"Deleting {lang.code} index.")
            old_count = ConferenceLookup.objects.filter(language=lang.code).count()
            ConferenceLookup.objects.filter(language=lang.code).delete()
            self.console.print(f"Fetching {lang.code} objects.")
            regex_query = Q(name__iregex=lang.regex) | Q(description__iregex=lang.regex)
            lookup_objects = [
                ConferenceLookup(conference=conference, language=lang.code)
                for conference in Conference.objects.filter(
                    regex_query,
                )
            ]
            self.console.print(
                f"Indexing {len(lookup_objects)} conferences for {lang.code}. Diff {len(lookup_objects) - old_count}."
            )
            ConferenceLookup.objects.bulk_create(lookup_objects)

        self.console.print("Done 🎉")
