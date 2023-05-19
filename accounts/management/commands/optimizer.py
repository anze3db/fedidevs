from django_rich.management import RichCommand

from accounts.models import Account, AccountLookup


class Command(RichCommand):
    help = "Crawles the fosstodon.org API and saves all accounts to the database"

    def handle(self, *args, **options):
        ids = AccountLookup.objects.values_list("account_id", flat=True).distinct()
        total = Account.objects.exclude(id__in=ids).count()
        self.console.print(f"Deleting {total}")
        Account.objects.exclude(id__in=ids).delete()
