from dataclasses import dataclass
from datetime import timedelta

from django.contrib.humanize.templatetags.humanize import naturaltime
from django.db import models


@dataclass
class Language:
    code: str
    name: str
    emoji: str
    regex: str


LANGUAGES = [
    Language("python", "Python", "🐍", r"python"),
    Language("javascript", "JavaScript", "📜", r"javascript"),
    Language("ruby", "Ruby", "💎", r"ruby"),
    Language("rust", "Rust", "🦀", r"[^a-z:]rust"),  # Filters out trust, etc.
    Language("golang", "Go", "🐹", r"golang"),
    Language("php", "PHP", "🐘", r"php"),
    Language("nix", "Nix", "❄️", r"[^a-z:]nix"),  # Filters out unix, linux, etc.
]


class Account(models.Model):
    username = models.TextField()
    acct = models.TextField()
    display_name = models.TextField()

    locked = models.BooleanField()
    bot = models.BooleanField()
    discoverable = models.BooleanField()
    group = models.BooleanField()
    noindex = models.BooleanField(null=True, blank=True)

    created_at = models.DateTimeField()
    last_status_at = models.DateTimeField(null=True, blank=True)
    last_sync_at = models.DateTimeField()

    followers_count = models.IntegerField()
    following_count = models.IntegerField()
    statuses_count = models.IntegerField()

    note = models.TextField()
    url = models.URLField()
    avatar = models.URLField()
    avatar_static = models.URLField()
    header = models.URLField()
    header_static = models.URLField()

    emojis = models.JSONField()
    roles = models.JSONField()
    fields = models.JSONField()

    def __str__(self):
        return self.username

    @property
    def source(self):
        return self.url.split("/")[2]

    @property
    def last_status_at_cached(self):
        if self.last_status_at is None:
            return "Never posted"

        from django.utils import timezone

        if timezone.now() - self.last_status_at < timedelta(days=7):
            return "Less than a week ago"

        # use natural time to display last status
        return naturaltime(self.last_status_at)


class AccountLookup(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    language = models.CharField(
        max_length=55,
        choices=[(lang.code, lang.name) for lang in LANGUAGES],
    )

    class Meta:
        indexes = [
            models.Index(fields=["language"]),
        ]
