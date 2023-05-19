from django_rich.management import RichCommand

from accounts.models import Account, AccountLookup


class Command(RichCommand):
    help = "Crawles the fosstodon.org API and saves all accounts to the database"

    def handle(self, *args, **options):
        ids = list(
            AccountLookup.objects.values_list("account_id", flat=True).distinct()
        )
        ids += list(
            Account.objects.filter(instance="oldbytes.space").values_list(
                "account_id", flat=True  # Don't delete oldbytes.space accounts
            )
        )
        total = Account.objects.exclude(id__in=ids).count()
        self.console.print(f"Deleting {total}")
        Account.objects.exclude(id__in=ids).delete()
