from textwrap import dedent

from django.core.mail import send_mail
from django.utils import timezone
from django_rich.management import RichCommand

from stats.models import Daily, store_daily_stats


class Command(RichCommand):
    help = "Gather daily stats"

    def handle(self, *args, **options):
        self.console.print("Gathering daily stats")
        store_daily_stats()
        self.send_email_report()

    def send_email_report(self):
        todays_date = timezone.now().date()
        today, yesterday = Daily.objects.filter().order_by("-date")[:2]
        send_mail(
            f"Fedidevs daily stats for {todays_date.isoformat()}",
            dedent(
                f"""
                    Number of accounts today {today.total_accounts} ({today.total_accounts - yesterday.total_accounts:+})
                    Number of posts today {today.total_posts} ({today.total_posts - yesterday.total_posts:+})
                    Number of python accounts today {today.python_accounts} ({today.python_accounts - yesterday.python_accounts:+})
                    Number of python posts today {today.python_posts} ({today.python_posts - yesterday.python_posts:+})"""
            ),
            "anze@fedidevs.com",
            ["anze@pecar.me"],
            fail_silently=False,
        )
