import json
import re
from dataclasses import dataclass
from datetime import timedelta

from django.contrib.humanize.templatetags.humanize import naturaltime
from django.db import models
from django.utils import timezone


@dataclass
class Language:
    code: str
    name: str
    emoji: str
    regex: str
    image: str

    only_bio: bool = False

    def post_code(self):
        return f"{self.code}-posts"


@dataclass
class Framework:
    code: str
    name: str
    emoji: str
    regex: str
    image: str

    only_bio: bool = False

    def post_code(self):
        return f"{self.code}-posts"


FRAMEWORKS = [
    Framework("django", "Django", "🐍", r"django", "frameworks/django.svg"),
    Framework("flask", "Flask", "🍶", r"flask", "frameworks/flask.png"),
    Framework("fastapi", "FastAPI", "🚀", r"fastapi", "frameworks/fastapi.svg"),
    Framework("rails", "Rails", "🛤️", r"rails", "frameworks/rails.png"),
    Framework("laravel", "Laravel", "🎣", r"laravel", "frameworks/laravel.png"),
    Framework("symfony", "Symfony", "🎻", r"symfony", "frameworks/symfony.png"),
    Framework("kubernetes", "Kubernetes", "🎻", r"kubernetes", "frameworks/kubernetes.png"),
    Framework("spring", "Spring", "🌱", r"spring", "frameworks/spring.png"),
    Framework("htmx", "HTMX", "🧬", r"htmx", "frameworks/htmx.png"),
    Framework("react", "React", "⚛️", r"react", "frameworks/react.png"),
    Framework("vue", "Vue", "🎨", r"[^a-z:]vue", "frameworks/vue.png"),
    Framework("angular", "Angular", "🅰️", r"angular", "frameworks/angular.png"),
    Framework("nextjs", "Next.js", "🖖", r"nextjs", "frameworks/nextjs.svg"),
    Framework("svelte", "Svelte", "🎬", r"svelte", "frameworks/svelte.png"),
    Framework("tailwind", "Tailwind", "🐱", r"tailwind", "frameworks/tailwind.svg"),
    Framework("bootstrap", "Bootstrap", "🥾", r"bootstrap", "frameworks/bootstrap.png"),
    Framework("dotnet", ".NET", "🌐", r" \.net|dotnet", "frameworks/dotnet.png"),
    Framework(
        "opensource",
        "Open Source",
        "📖",
        r"open[- _]?source|free[- _]?software|libre[- _]?software|foss[^i]",
        "languages/opensource.png",
    ),
    Framework("linux", "Linux", "🐧", r"linux", "languages/linux.png"),
]

LANGUAGES = [
    Language("python", "Python", "🐍", r"python|psf|django", "languages/python.png"),
    Language(
        "typescript",
        "TypeScript",
        "📜",
        r"typescript|[^a-z]ts[^a-z:]",
        "languages/typescript.png",
    ),
    Language(
        "javascript",
        "JavaScript",
        "📜",
        r"javascript|[^a-z]js[^a-z:]",
        "languages/javascript.png",
    ),
    Language("rust", "Rust", "🦀", r"[^a-z:]rust[^a-z]|rustlang", "languages/rust.png"),  # Filters out trust, etc.
    Language("ruby", "Ruby", "💎", r"ruby", "languages/ruby.png"),
    Language("golang", "Golang", "🐹", r"golang", "languages/golang.png"),
    Language("java", "Java", "☕", r"java[^script]", "languages/java.png"),
    Language("kotlin", "Kotlin", "🤖", r"kotlin", "languages/kotlin.png"),
    Language("scala", "Scala", "🧪", r"[^e]scala[^b]", "languages/scala.png"),
    Language("swift", "Swift", "🐦", r"swift", "languages/swift.png"),
    Language("csharp", "C#", "♫", r"csharp|c#", "languages/csharp.png"),
    Language("fsharp", "F#", "♬", r"fsharp|f#", "languages/fsharp.png"),
    Language("cpp", "C++", "🐯", r"c\+\+|cpp", "languages/cpp.png"),
    Language("css", "CSS", "🦝", r"[^\.]css", "languages/css.svg"),
    Language("php", "PHP", "🐘", r"[^\.]php", "languages/php.png"),  # Filters out index.php? and others
    Language("haskell", "Haskell", "🦥", r"haskell", "languages/haskell.png"),
    Language("ocaml", "OCaml", "🐫", r"ocaml", "languages/ocaml.png"),
    Language(
        "nix", "Nix", "❄️", r"[^(a-z|\.|\*):]nix[^Craft]", "languages/nix.png"
    ),  # Filters out unix, linux, nixCraft, git.nix etc.
    Language("julia", "Julia", "📊", r"julia(?!n)", "languages/julia.png", only_bio=True),  # Filters out Julian
    # Language("gaming", "Gaming", "🎮", r"gaming|game", "languages/gaming.png"),
    # Language(
    #     "security",
    #     "Security",
    #     "🔒",
    #     r"security|infosec|appsec",
    #     "languages/security.png",
    # ),
]


class Account(models.Model):
    account_id = models.TextField()
    instance = models.TextField()

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

    class Meta:
        unique_together = (
            "account_id",
            "instance",
        )
        indexes = [
            models.Index(fields=["noindex", "discoverable"]),
        ]

    def __str__(self):
        return self.username

    @property
    def name(self):
        return self.display_name or self.username or self.acct

    @property
    def source(self):
        return self.url.split("/")[2]

    @property
    def last_status_at_cached(self):
        if self.last_status_at is None:
            return "Never posted"

        if timezone.now() - self.last_status_at < timedelta(days=1):
            return "Less than a day ago"

        # use natural time to display last status
        return naturaltime(self.last_status_at)

    @property
    def username_at_instance(self):
        return f"@{self.username}@{self.source}"

    @property
    def languages(self):
        lang_lookup = {lang.code: lang for lang in LANGUAGES + FRAMEWORKS}
        return [lang_lookup[lang.language] for lang in self.accountlookup_set.all()]

    def should_index(self):
        if self.noindex or not self.discoverable:
            return False

        if self.followers_count == 0 and self.statuses_count == 0 and self.following_count == 0:
            return False

        for lang in LANGUAGES + FRAMEWORKS:
            for field in (self.note, self.display_name, json.dumps(self.fields)):
                if re.search(lang.regex, field, re.IGNORECASE):
                    return True

        return False


class AccountLookup(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    language = models.CharField(
        max_length=55,
        choices=[(lang.code, lang.name) for lang in LANGUAGES],
    )
