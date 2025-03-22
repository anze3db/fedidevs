from django.db.models import Count, Q
from django.utils import timezone
from django_rich.management import RichCommand

from starter_packs.models import StarterPack


def starter_pack_stats():
    now = timezone.now()
    starter_packs = StarterPack.objects.all()

    for starter_pack in starter_packs:
        follow_counts = starter_pack.followallclick_set.aggregate(
            daily_follows=Count("user_id", distinct=True, filter=Q(created_at__gt=now - timezone.timedelta(days=1))),
            weekly_follows=Count("user_id", distinct=True, filter=Q(created_at__gt=now - timezone.timedelta(days=7))),
            monthly_follows=Count("user_id", distinct=True, filter=Q(created_at__gt=now - timezone.timedelta(days=30))),
        )

        # Apply the counts to the starter_pack object
        starter_pack.daily_follows = follow_counts["daily_follows"]
        starter_pack.weekly_follows = follow_counts["weekly_follows"]
        starter_pack.monthly_follows = follow_counts["monthly_follows"]

    StarterPack.objects.bulk_update(starter_packs, ["daily_follows", "weekly_follows", "monthly_follows"])


class Command(RichCommand):
    help = "Gather daily starter pack stats"

    def handle(self, *args, **options):
        self.console.print("Computing starter pack stats")
        starter_pack_stats()
