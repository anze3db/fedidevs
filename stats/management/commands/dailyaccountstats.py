from django.utils import timezone
from django_rich.management import RichCommand

from accounts.models import Account
from stats.models import DailyAccount


class Command(RichCommand):
    help = "Insert daily account stats"

    def handle(self, *args, **options):
        self.console.print("Insert account stats")
        accounts = Account.objects.all().only(
            "id",
            "followers_count",
            "following_count",
            "statuses_count",
        )
        todays_date = timezone.now().date()
        DailyAccount.objects.filter(date=todays_date).delete()
        daily_accounts = [
            DailyAccount(
                account=account,
                date=todays_date,
                followers_count=account.followers_count,
                following_count=account.following_count,
                statuses_count=account.statuses_count,
            )
            for account in accounts
        ]
        DailyAccount.objects.bulk_create(daily_accounts, batch_size=5000)
        self.console.print(f"{len(daily_accounts)} daily account stats created")
