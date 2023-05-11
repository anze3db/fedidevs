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
    image: str


LANGUAGES = [
    Language("python", "Python", "🐍", r"python|psf", "languages/python.png"),
    Language(
        "javascript",
        "JavaScript",
        "📜",
        r"javascript|js[^a-z:]|typescript",
        "languages/javascript.png",
    ),
    Language(
        "rust", "Rust", "🦀", r"[^a-z:]rust", "languages/rust.png"
    ),  # Filters out trust, etc.
    Language("ruby", "Ruby", "💎", r"ruby", "languages/ruby.png"),
    Language("java", "Java", "☕", r"java[^script]", "languages/java.png"),
    Language("csharp", "C#", "♫", r"csharp|c#", "languages/csharp.png"),
    Language("kotlin", "Kotlin", "🤖", r"kotlin", "languages/kotlin.png"),
    Language("fsharp", "F#", "♬", r"fsharp|f#", "languages/fsharp.png"),
    Language("scala", "Scala", "🧪", r"[^e]scala[^b]", "languages/scala.png"),
    Language("golang", "Golang", "🐹", r"golang", "languages/golang.png"),
    Language("php", "PHP", "🐘", r"php", "languages/php.png"),
    Language("linux", "Linux", "🐧", r"linux", "languages/linux.png"),
    Language("haskell", "Haskell", "🦥", r"haskell", "languages/haskell.png"),
    Language(
        "nix", "Nix", "❄️", r"[^a-z:]nix", "languages/nix.png"
    ),  # Filters out unix, linux, etc.
    Language(
        "opensource",
        "Open Source",
        "📖",
        r"open[- _]?source|free[- _]?software|libre[- _]?software",
        "languages/opensource.png",
    ),
    Language("gaming", "Gaming", "🎮", r"gaming|game", "languages/gaming.png"),
    Language(
        "security",
        "Security",
        "🔒",
        r"security|infosec|appsec",
        "languages/security.png",
    ),
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
    last_status_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_sync_at = models.DateTimeField()

    followers_count = models.IntegerField(db_index=True)
    following_count = models.IntegerField()
    statuses_count = models.IntegerField(db_index=True)

    note = models.TextField()
    url = models.URLField(db_index=True)
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


class AccountLookupAny(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
