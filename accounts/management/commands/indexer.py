from django_rich.management import RichCommand

from accounts.models import LANGUAGES, Account, AccountLookup


class Command(RichCommand):
    help = "Crawles the fosstodon.org API and saves all accounts to the database"

    def handle(self, *args, **options):
        for lang in LANGUAGES:
            self.console.print(f"Deleting {lang.code} index.")
            AccountLookup.objects.filter(language=lang.code).delete()
            self.console.print(f"Fetching {lang.code} objects.")
            lookup_objects = [
                AccountLookup(account=account, language=lang.code)
                for account in Account.objects.filter(note__iregex=lang.regex)
            ]
            self.console.print(f"Creating {lang.code} index.")
            AccountLookup.objects.bulk_create(lookup_objects)
