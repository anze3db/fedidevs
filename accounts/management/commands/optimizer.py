from django_rich.management import RichCommand

from accounts.models import Account, AccountLookup


class Command(RichCommand):
    help = "Crawles the fosstodon.org API and saves all accounts to the database"

    def handle(self, *args, **options):
        account_ids = set(AccountLookup.objects.values_list("account_id", flat=True).distinct())
        # post_ids = set(Post.objects.values_list("account_id", flat=True).distinct())
        # ids = account_ids | post_ids
        total = Account.objects.exclude(id__in=account_ids).count()
        self.console.print(f"Deleting {total}")
        Account.objects.exclude(id__in=account_ids).delete()
        self.console.print("Done")
