import datetime as dt
from collections import defaultdict

from django.db.models import Q
from django.utils import timezone
from django_rich.management import RichCommand

from accounts.models import FRAMEWORKS, LANGUAGES, Account, AccountLookup


class Command(RichCommand):
    help = "Indexes accounts in the database"

    def handle(self, *args, **options):
        languages_for_account: dict[Account, set[str]] = defaultdict(set)

        for lang in LANGUAGES + FRAMEWORKS:
            if lang.only_bio:
                regex_query = Q(note__iregex=lang.regex)
            else:
                regex_query = (
                    Q(note__iregex=lang.regex) | Q(display_name__iregex=lang.regex) | Q(fields__iregex=lang.regex)
                )
            for account in Account.objects.filter(
                regex_query,
                discoverable=True,
                noindex=False,
                last_status_at__gt=timezone.now() - dt.timedelta(days=230),
            ):
                languages_for_account[account].add(lang.code)

        # Delete lookups that are no longer relevant
        AccountLookup.objects.exclude(account_id__in={account.id for account in languages_for_account.keys()}).delete()

        # Existing lookups
        existing_lookups = AccountLookup.objects.prefetch_related("account").all()
        existing_lookups_dict = {lookup.account: lookup for lookup in existing_lookups}

        update_lookups = []
        create_lookups = []
        for account, languages in languages_for_account.items():
            if account in existing_lookups_dict:
                lookup = existing_lookups_dict[account]
                update_lookups.append(lookup)
            else:
                lookup = AccountLookup(account=account)
                create_lookups.append(lookup)

            lookup.language = "\n".join(languages)
            lookup.last_status_at = account.last_status_at
            lookup.followers_count = account.followers_count
            lookup.text = "\n".join([account.note, account.display_name, account.username, account.url])

            lookup.statuses_count = account.statuses_count
            lookup.followers_count = account.followers_count
            lookup.following_count = account.following_count

        AccountLookup.objects.bulk_create(create_lookups, batch_size=100)
        AccountLookup.objects.bulk_update(
            update_lookups,
            [
                "language",
                "last_status_at",
                "followers_count",
                "last_status_at",
                "followers_count",
                "text",
                "statuses_count",
                "followers_count",
                "following_count",
            ],
            batch_size=100,
        )
        self.console.print("Done 🎉")
