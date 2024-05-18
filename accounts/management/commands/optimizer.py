from django.db import connection
from django_rich.management import RichCommand

from accounts.models import Account, AccountLookup
from posts.models import Post


class Command(RichCommand):
    help = "Crawles the fosstodon.org API and saves all accounts to the database"

    def handle(self, *args, **options):
        account_ids = set(AccountLookup.objects.values_list("account_id", flat=True).distinct())
        post_ids = set(Post.objects.values_list("account_id", flat=True).distinct())
        ids = account_ids | post_ids
        total = Account.objects.exclude(id__in=ids).count()
        self.console.print(f"Deleting {total}")
        self.console.print(f"Accounts from posts that don't have a lookup: {len(post_ids - account_ids)}")
        Account.objects.exclude(id__in=ids).delete()
        with connection.cursor() as cursor:
            cursor.execute("VACUUM")  # TODO: This makes the wal file large. Might be unecessary
        self.console.print("Done")
