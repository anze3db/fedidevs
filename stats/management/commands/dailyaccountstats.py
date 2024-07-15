import datetime as dt
from textwrap import dedent
from typing import List

from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.utils import timezone
from django_rich.management import RichCommand

from accounts.models import Account
from stats.models import (
    Daily,
    DailyAccount,
    DailyAccountChange,
    DailySite,
    FollowClick,
    MonthlyAccountChange,
    WeeklyAccountChange,
)

UPDATE_BATCH_SIZE = 100
CREATE_BATCH_SIZE = 1000


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
        DailyAccount.objects.bulk_create(daily_accounts, batch_size=CREATE_BATCH_SIZE)
        self.console.print(f"{len(daily_accounts)} daily account stats created")

        self.calculate_period_stats(daily_accounts, self.get_prev_date(1), DailyAccountChange)
        self.calculate_period_stats(daily_accounts, self.get_prev_date(7), WeeklyAccountChange)
        self.calculate_period_stats(daily_accounts, self.get_prev_date(30), MonthlyAccountChange)
        self.send_email_report()

    def get_prev_date(self, days_ago: int):
        """
        Return date from 'days_ago' days back if Daily object for that date exists,
        else return closest possible date.
        """
        todays_date = timezone.now().date()
        dates_count = DailyAccount.objects.values("date").distinct().count()
        if dates_count < 2:
            return todays_date - timezone.timedelta(days=1)
        if dates_count < days_ago:
            return todays_date - timezone.timedelta(days=dates_count - 1)
        return todays_date - timezone.timedelta(days=days_ago)

    def calculate_period_stats(
        self,
        daily_accounts: List[DailyAccount],
        prev_date: dt.date,
        acc_change_class: type[DailyAccountChange] | type[WeeklyAccountChange] | type[MonthlyAccountChange],
    ):
        prev_date_account_counts = {
            da["account_id"]: da
            for da in DailyAccount.objects.filter(date=prev_date).values(
                "account_id",
                "followers_count",
                "following_count",
                "statuses_count",
            )
        }

        daily_change_counts = {dac.account_id: dac for dac in acc_change_class.objects.all()}
        to_update = []
        to_create = []
        for daily_account in daily_accounts:
            prev_date_count = prev_date_account_counts.get(
                daily_account.account_id,
                {
                    "followers_count": daily_account.followers_count,
                    "following_count": daily_account.following_count,
                    "statuses_count": daily_account.statuses_count,
                },
            )

            prev_followers_count = prev_date_count["followers_count"]
            prev_following_count = prev_date_count["following_count"]
            prev_statuses_count = prev_date_count["statuses_count"]

            if daily_account.account_id not in daily_change_counts:
                daily_account_change = acc_change_class(
                    account_id=daily_account.account_id,
                    followers_count=daily_account.followers_count - prev_followers_count,
                    following_count=daily_account.following_count - prev_following_count,
                    statuses_count=daily_account.statuses_count - prev_statuses_count,
                )
                to_create.append(daily_account_change)
                continue

            daily_account_change = daily_change_counts[daily_account.account_id]

            if (
                daily_account.followers_count == prev_followers_count
                and daily_account.following_count == prev_following_count
                and daily_account.statuses_count == prev_statuses_count
            ):
                # no change
                continue
            daily_account_change.followers_count = daily_account.followers_count - prev_followers_count
            daily_account_change.following_count = daily_account.following_count - prev_following_count
            daily_account_change.statuses_count = daily_account.statuses_count - prev_statuses_count
            to_update.append(daily_account_change)

        if to_create:
            acc_change_class.objects.bulk_create(to_create, batch_size=CREATE_BATCH_SIZE)
            self.console.print(f"{len(to_create)} new account changes created")
        if to_update:
            acc_change_class.objects.bulk_update(
                to_update, ["followers_count", "following_count", "statuses_count"], batch_size=UPDATE_BATCH_SIZE
            )
            self.console.print(f"{len(to_update)} account changes updated")

    def send_email_report(self):
        todays_date = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        yesterdays_date = todays_date - timezone.timedelta(days=1)
        week_ago = todays_date - timezone.timedelta(days=7)
        month_ago = todays_date - timezone.timedelta(days=30)
        latest_daily = Daily.objects.filter().order_by("-date")
        if len(latest_daily) < 2:
            yesterday = self.create_yesterday()
            today = Daily.objects.filter().order_by("-date")[0]
        else:
            today, yesterday = latest_daily[:2]
        top_growing_daily = DailyAccountChange.objects.select_related("account").order_by("-followers_count")[:5]
        top_growing_daily = "\n".join(
            [f"{dac.followers_count:>6} {dac.account.username} {dac.account.url}" for dac in top_growing_daily]
        )

        top_growing_monthly = MonthlyAccountChange.objects.select_related("account").order_by("-followers_count")[:5]
        top_growing_monthly = "\n".join(
            [f"{mac.followers_count:>6} {mac.account.username} {mac.account.url}" for mac in top_growing_monthly]
        )

        auth_users_cnt = User.objects.filter(is_active=True).count()
        yesterday_auth_users_cnt = User.objects.filter(is_active=True, date_joined__gte=yesterdays_date).count()
        weekly_users_cnt = User.objects.filter(is_active=True, last_login__gte=week_ago).count()
        monthly_users_cnt = User.objects.filter(is_active=True, last_login__gte=month_ago).count()

        total_follows = FollowClick.objects.count()
        yesterday_total_follows = FollowClick.objects.filter(created_at__gte=yesterdays_date).count()
        weekly_follows_cnt = FollowClick.objects.filter(created_at__gte=week_ago).count()
        monthly_follows_cnt = FollowClick.objects.filter(created_at__gte=month_ago).count()

        DailySite.objects.update_or_create(
            date=todays_date,
            defaults={
                "total_users": auth_users_cnt,
                "daily_active_users": yesterday_auth_users_cnt,
                "weekly_active_users": weekly_users_cnt,
                "monthly_active_users": monthly_users_cnt,
                "total_follows": total_follows,
                "daily_follows": yesterday_total_follows,
                "weekly_follows": weekly_follows_cnt,
                "monthly_follows": monthly_follows_cnt,
            },
        )

        send_mail(
            f"Fedidevs daily stats for {todays_date.date().isoformat()}",
            dedent(
                f"""\
                    Total users {auth_users_cnt}, joined since yesterday {yesterday_auth_users_cnt}
                    Weekly active users {weekly_users_cnt}
                    Monthly active users {monthly_users_cnt}

                    Total follows {total_follows}, followed since yesterday {yesterday_total_follows}
                    Weekly follows {weekly_follows_cnt}
                    Monthly follows {monthly_follows_cnt}

                    Number of accounts today {today.total_accounts} ({today.total_accounts - yesterday.total_accounts:+})
                    Number of posts today {today.total_posts} ({today.total_posts - yesterday.total_posts:+})
                    Number of python accounts today {today.python_accounts} ({today.python_accounts - yesterday.python_accounts:+})
                    Number of python posts today {today.python_posts} ({today.python_posts - yesterday.python_posts:+})

                    Top growing daily accounts:
                    """
            )
            + top_growing_daily
            + "\n\nTop growing monthly accounts:\n"
            + top_growing_monthly,
            "anze@fedidevs.com",
            ["anze@pecar.me"],
            fail_silently=False,
        )

    def create_yesterday(self):
        self.console.print("Manually creating empty Daily object for yesterday")
        todays_date = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        yesterdays_date = todays_date - timezone.timedelta(days=1)
        return Daily(
            date=yesterdays_date.date(),
            total_accounts=0,
            python_accounts=0,
            javascript_accounts=0,
            rust_accounts=0,
            ruby_accounts=0,
            golang_accounts=0,
            java_accounts=0,
            kotlin_accounts=0,
            scala_accounts=0,
            swift_accounts=0,
            csharp_accounts=0,
            fsharp_accounts=0,
            dotnet_accounts=0,
            cpp_accounts=0,
            linux_accounts=0,
            haskell_accounts=0,
            ocaml_accounts=0,
            nix_accounts=0,
            opensource_accounts=0,
            php_accounts=0,
        )
