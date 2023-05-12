from django.db.models import Q
from django_rich.management import RichCommand

from accounts.models import LANGUAGES, Account, AccountLookup


class Command(RichCommand):
    help = "Crawles the fosstodon.org API and saves all accounts to the database"

    def handle(self, *args, **options):
        any_lookup = set()
        for lang in LANGUAGES:
            self.console.print(f"Deleting {lang.code} index.")
            old_count = AccountLookup.objects.filter(language=lang.code).count()
            AccountLookup.objects.filter(language=lang.code).delete()
            self.console.print(f"Fetching {lang.code} objects.")
            lookup_objects = [
                AccountLookup(account=account, language=lang.code)
                for account in Account.objects.filter(
                    (Q(note__iregex=lang.regex) | Q(display_name__iregex=lang.regex)),
                    discoverable=True,
                    noindex=False,
                )
            ]
            any_lookup |= {lookup.account.id for lookup in lookup_objects}
            self.console.print(
                f"Indexing {len(lookup_objects)} accounts for {lang.code}. Diff {len(lookup_objects) - old_count}."
            )
            AccountLookup.objects.bulk_create(lookup_objects)

        self.console.print("Done 🎉")
