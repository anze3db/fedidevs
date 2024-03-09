from textwrap import dedent

from django.core.mail import send_mail
from django.utils import timezone
from django_rich.management import RichCommand

from accounts.models import Account
from stats.models import Daily, DailyAccount, DailyAccountChange


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

        yesterdays_date = todays_date - timezone.timedelta(days=1)
        yesterdays_account_counts = {
            da["account_id"]: da
            for da in DailyAccount.objects.filter(date=yesterdays_date).values(
                "account_id",
                "followers_count",
                "following_count",
                "statuses_count",
            )
        }

        daily_change_counts = {dac.account_id: dac for dac in DailyAccountChange.objects.all()}
        to_update = []
        to_create = []
        for daily_account in daily_accounts:
            if daily_account.account_id not in daily_change_counts:
                daily_account_change = DailyAccountChange(
                    account_id=daily_account.account_id,
                    followers_count=0,
                    following_count=0,
                    statuses_count=0,
                )
                to_create.append(daily_account_change)
                continue

            daily_account_change = daily_change_counts[daily_account.account_id]

            yesterday_count = yesterdays_account_counts.get(
                daily_account_change.account_id,
                {
                    "followers_count": daily_account.followers_count,
                    "following_count": daily_account.following_count,
                    "statuses_count": daily_account.statuses_count,
                },
            )

            prev_followers_count = yesterday_count["followers_count"]
            prev_following_count = yesterday_count["following_count"]
            prev_statuses_count = yesterday_count["statuses_count"]

            if (
                daily_account.followers_count == prev_followers_count
                or daily_account.following_count == prev_following_count
                or daily_account.statuses_count == prev_statuses_count
            ):
                # no change
                continue
            daily_account_change.followers_count = daily_account.followers_count - prev_followers_count
            daily_account_change.following_count = daily_account.following_count - prev_following_count
            daily_account_change.statuses_count = daily_account.statuses_count - prev_statuses_count
            to_update.append(daily_account_change)

        if to_create:
            DailyAccountChange.objects.bulk_create(to_create, batch_size=5000)
            self.console.print(f"{len(to_create)} new daily account changes created")
        if to_update:
            DailyAccountChange.objects.bulk_update(
                to_update, ["followers_count", "following_count", "statuses_count"], batch_size=5000
            )
            self.console.print(f"{len(to_update)} daily account changes updated")

        self.send_email_report()

    def send_email_report(self):
        todays_date = timezone.now().date()
        today, yesterday = Daily.objects.filter().order_by("-date")[:2]
        top_growing = DailyAccountChange.objects.select_related("account").order_by("-followers_count")[:5]
        top_growing = "\n".join(
            [f"{dac.followers_count:>6} {dac.account.username} {dac.account.url}" for dac in top_growing]
        )
        send_mail(
            f"Fedidevs daily stats for {todays_date.isoformat()}",
            dedent(
                f"""
                    Number of accounts today {today.total_accounts} ({today.total_accounts - yesterday.total_accounts:+})
                    Number of posts today {today.total_posts} ({today.total_posts - yesterday.total_posts:+})
                    Number of python accounts today {today.python_accounts} ({today.python_accounts - yesterday.python_accounts:+})
                    Number of python posts today {today.python_posts} ({today.python_posts - yesterday.python_posts:+})

                    Top growing accounts:
                    """
            )
            + top_growing,
            "anze@fedidevs.com",
            ["anze@pecar.me"],
            fail_silently=False,
        )
