import datetime as dt
import zoneinfo

from django.db import models

from accounts.models import Framework, Language

FRAMEWORKS = [
    Framework("django", "Django", "🐍", r"django", "frameworks/django.png"),
    Framework("flask", "Flask", "🍶", r"flask", "frameworks/flask.png"),
    Framework("fastapi", "FastAPI", "🚀", r"fastapi", "frameworks/fastapi.png"),
    Framework("rails", "Rails", "🛤️", r"rails", "frameworks/rails.png"),
    Framework("laravel", "Laravel", "🎣", r"laravel", "frameworks/laravel.png"),
    Framework("symfony", "Symfony", "🎻", r"symfony", "frameworks/symfony.png"),
    Framework("kubernetes", "Kubernetes", "🎻", r"kubernetes", "frameworks/kubernetes.png"),
    Framework("spring", "Spring", "🌱", r"spring", "frameworks/spring.png"),
    Framework("htmx", "HTMX", "🧬", r"htmx", "frameworks/htmx.png"),
    Framework("react", "React", "⚛️", r"react", "frameworks/react.png"),
    Framework("vue", "Vue", "🎨", r"[^a-z:]vue", "frameworks/vue.png"),
    Framework("angular", "Angular", "🅰️", r"angular", "frameworks/angular.png"),
    Framework("nextjs", "Next.js", "🖖", r"nextjs", "frameworks/nextjs.png"),
    Framework("svelte", "Svelte", "🎬", r"svelte", "frameworks/svelte.png"),
    Framework("tailwind", "Tailwind", "🐱", r"tailwind", "frameworks/tailwind.png"),
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
    Framework("security", "Security", "🔒", r"security|infosec|appsec|OSCP|OSWP", "frameworks/security.png"),
    Framework(
        "machinelearning", "Machine Learning", "🤖", r"machine[- _]?learning|ML|AI", "frameworks/machine-learning.jpg"
    ),
    Framework("bsd", "BSD", "😈", r"bsd", "frameworks/bsd.png"),
    Framework("android", "Android", "🤖", r"roboto|android", "frameworks/android.png"),
    Framework("postgres", "Postgres", "🐧", r"postgres|pg", "frameworks/postgres.png"),
    Framework("flutter", "Flutter", "🐤", r"flutter", "frameworks/flutter.png"),
]

LANGUAGES = [
    Language("python", "Python", "🐍", r"python|psf|pycon|py", "languages/python.png"),
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
        r"javascript|jsconf|js",
        "languages/javascript.png",
    ),
    Language("rust", "Rust", "🦀", r"[^a-z:]rust[^a-z]|rustlang", "languages/rust.png"),  # Filters out trust, etc.
    Language("ruby", "Ruby", "💎", r"ruby", "languages/ruby.png"),
    Language("golang", "Golang", "🐹", r"golang|golab", "languages/golang.png"),
    Language("java", "Java", "☕", r"java[^script]", "languages/java.png"),
    Language("kotlin", "Kotlin", "🤖", r"kotlin", "languages/kotlin.png"),
    Language("scala", "Scala", "🧪", r"[^e]scala[^b]", "languages/scala.png"),
    Language("swift", "Swift", "🐦", r"swift|ios|apple", "languages/swift.png"),
    Language("csharp", "C#", "♫", r"csharp|c#", "languages/csharp.png"),
    Language("fsharp", "F#", "♬", r"fsharp|f#", "languages/fsharp.png"),
    Language("cpp", "C++", "🐯", r"c\+\+|cpp", "languages/cpp.png"),
    Language("css", "CSS", "🦝", r"[^\.]css", "languages/css.png"),
    Language("php", "PHP", "🐘", r"php", "languages/php.png"),  # Filters out index.php? and others
    Language("haskell", "Haskell", "🦥", r"haskell", "languages/haskell.png"),
    Language("ocaml", "OCaml", "🐫", r"ocaml", "languages/ocaml.png"),
    Language(
        "nix", "Nix", "❄️", r"[^(a-z|\.|\*):]nix[^Craft]", "languages/nix.png"
    ),  # Filters out unix, linux, nixCraft, git.nix etc.
    Language("julia", "Julia", "📊", r"julia(?!n)", "languages/julia.png", only_bio=True),  # Filters out Julian
    Language("odin", "Odin", "📊", r"[^(a-z)]odin[^(a-z)]|odin-?lang", "languages/odin.png"),
    # Language("gaming", "Gaming", "🎮", r"gaming|game", "languages/gaming.png"),
    # Language(
    #     "security",
    #     "Security",
    #     "🔒",
    #     r"security|infosec|appsec",
    #     "languages/security.png",
    # ),
]


class Conference(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    location = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()

    timezone_choices = models.TextChoices("Timezone", " ".join(sorted(zoneinfo.available_timezones())))
    time_zone = models.CharField(max_length=255, default="UTC", choices=timezone_choices.choices)

    archived_date = models.DateField(null=True, blank=True)

    website = models.URLField(default="")
    mastodon = models.URLField(default="", blank=True)

    description = models.TextField()

    posts_after = models.DateField(null=True, blank=True)
    instances = models.TextField(
        default="",
        help_text="Comma seperated list of instances, e.g. fosstodon.org, mastodon.social. Automatically computed",
    )
    tags = models.TextField(default="", help_text="Comma seperated list of tags, e.g. #djangocon")  # hashtags
    days = models.TextField(
        default="",
        help_text="Comma seperated list of conference day names, e.g. Tutorials, Tutorials, Talks, Talks",
        blank=True,
    )  # names for conference days
    day_styles = models.TextField(
        default="",
        help_text="Comma seperated list of style names for each day, e.g. blue, blue, red, red, green, green (if not color is set the day will be purple)",
        blank=True,
    )

    accounts = models.ManyToManyField("accounts.Account", blank=True, through="ConferenceAccount")
    posts = models.ManyToManyField("posts.Post", blank=True, through="ConferencePost")

    def __str__(self):
        return self.name

    @property
    def posts_after_datetime(self) -> dt.datetime | None:
        """`posts_after` (a date) as a timezone-aware datetime at the start of that
        day in the conference's timezone.

        Used for `created_at__gte` filters against DateTimeField columns: passing a
        bare `date` makes Django coerce it to a *naive* datetime and warn under
        active time zone support.
        """
        if not self.posts_after:
            return None
        return dt.datetime.combine(self.posts_after, dt.time.min, tzinfo=zoneinfo.ZoneInfo(self.time_zone))

    @property
    def languages(self):
        lang_lookup = {lang.code: lang for lang in LANGUAGES + FRAMEWORKS}
        return [lang_lookup[lang.language] for lang in self.conferencelookup_set.all()]


class ConferenceLookup(models.Model):
    conference = models.ForeignKey(Conference, on_delete=models.CASCADE)
    language = models.CharField(
        max_length=55,
        choices=[(lang.code, lang.name) for lang in LANGUAGES + FRAMEWORKS],
    )

    def __str__(self):
        return self.language


class ConferenceAccount(models.Model):
    conference = models.ForeignKey(Conference, on_delete=models.CASCADE)
    account = models.ForeignKey("accounts.Account", on_delete=models.CASCADE)
    count = models.IntegerField(default=0)

    class Meta:
        unique_together = ("conference", "account")


class ConferencePost(models.Model):
    conference = models.ForeignKey(Conference, on_delete=models.CASCADE)
    post = models.ForeignKey("posts.Post", on_delete=models.CASCADE)
    # Fields to be sorted on
    created_at = models.DateTimeField(null=True, blank=True)
    favourites_count = models.IntegerField(null=True, blank=True)
    reblogs_count = models.IntegerField(null=True, blank=True)
    replies_count = models.IntegerField(null=True, blank=True)
    visibility = models.TextField(null=True, blank=True)
    account = models.ForeignKey("accounts.Account", on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        unique_together = ("conference", "post")
        indexes = [
            models.Index(fields=["conference", "created_at"]),
            models.Index(fields=["conference", "favourites_count"]),
            models.Index(fields=["conference", "reblogs_count"]),
            models.Index(fields=["conference", "replies_count"]),
            models.Index(fields=["conference", "account", "created_at"]),
            models.Index(fields=["conference", "account", "favourites_count"]),
            models.Index(fields=["conference", "account", "reblogs_count"]),
            models.Index(fields=["conference", "account", "replies_count"]),
        ]


class ConferenceTag(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    icon = models.CharField(max_length=255)


class MinId(models.Model):
    conference = models.ForeignKey(Conference, on_delete=models.CASCADE)
    instance = models.TextField()
    min_id = models.CharField(default="0", max_length=255)

    class Meta:
        unique_together = ("conference", "instance")


class Fwd50Account(models.Model):
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
        constraints = [models.UniqueConstraint(fields=["url"], name="unique_account_url")]
        indexes = [
            models.Index(fields=["noindex", "discoverable"]),
        ]

    def __str__(self):
        return self.username

    @property
    def source(self):
        return self.url.split("/")[2]


class Fwd50Post(models.Model):
    post_id = models.TextField()
    account = models.ForeignKey(Fwd50Account, on_delete=models.CASCADE, related_name="posts")
    instance = models.TextField()

    created_at = models.DateTimeField()
    in_reply_to_id = models.TextField(null=True, blank=True)
    in_reply_to_account_id = models.TextField(null=True, blank=True)

    sensitive = models.BooleanField(null=True, blank=True)
    spoiler_text = models.TextField(null=True, blank=True)
    visibility = models.TextField()
    language = models.TextField(null=True, blank=True)
    uri = models.URLField()
    url = models.URLField()
    replies_count = models.IntegerField()
    reblogs_count = models.IntegerField()
    favourites_count = models.IntegerField()
    edited_at = models.DateTimeField(null=True, blank=True)
    content = models.TextField()
    reblog = models.TextField(null=True, blank=True)
    application = models.JSONField(null=True, blank=True)
    media_attachments = models.JSONField(default=list)
    mentions = models.JSONField(default=list)
    tags = models.JSONField(default=list)
    emojis = models.JSONField(default=list)
    card = models.JSONField(null=True, blank=True)
    poll = models.JSONField(null=True, blank=True)

    class Meta:
        unique_together = ("post_id", "instance")
        constraints = [models.UniqueConstraint(fields=["url"], name="unique_post_url")]


class DjangoConAfricaAccount(models.Model):
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
        constraints = [models.UniqueConstraint(fields=["url"], name="unique_djangoconafrica_url")]
        indexes = [
            models.Index(fields=["noindex", "discoverable"]),
        ]

    def __str__(self):
        return self.username

    @property
    def source(self):
        return self.url.split("/")[2]


class DjangoConAfricaPost(models.Model):
    post_id = models.TextField()
    account = models.ForeignKey(DjangoConAfricaAccount, on_delete=models.CASCADE, related_name="posts")
    instance = models.TextField()

    created_at = models.DateTimeField()
    in_reply_to_id = models.TextField(null=True, blank=True)
    in_reply_to_account_id = models.TextField(null=True, blank=True)

    sensitive = models.BooleanField(null=True, blank=True)
    spoiler_text = models.TextField(null=True, blank=True)
    visibility = models.TextField()
    language = models.TextField(null=True, blank=True)
    uri = models.URLField()
    url = models.URLField()
    replies_count = models.IntegerField()
    reblogs_count = models.IntegerField()
    favourites_count = models.IntegerField()
    edited_at = models.DateTimeField(null=True, blank=True)
    content = models.TextField()
    reblog = models.TextField(null=True, blank=True)
    application = models.JSONField(null=True, blank=True)
    media_attachments = models.JSONField(default=list)
    mentions = models.JSONField(default=list)
    tags = models.JSONField(default=list)
    emojis = models.JSONField(default=list)
    card = models.JSONField(null=True, blank=True)
    poll = models.JSONField(null=True, blank=True)

    class Meta:
        unique_together = ("post_id", "instance")
        constraints = [models.UniqueConstraint(fields=["url"], name="unique_post_djangoconafrica_url")]


class DotNetConfAccount(models.Model):
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
        constraints = [models.UniqueConstraint(fields=["url"], name="unique_dotnetcon_url")]
        indexes = [
            models.Index(fields=["noindex", "discoverable"]),
        ]

    def __str__(self):
        return self.username

    @property
    def source(self):
        return self.url.split("/")[2]


class DotNetConfPost(models.Model):
    post_id = models.TextField()
    account = models.ForeignKey(DotNetConfAccount, on_delete=models.CASCADE, related_name="posts")
    instance = models.TextField()

    created_at = models.DateTimeField()
    in_reply_to_id = models.TextField(null=True, blank=True)
    in_reply_to_account_id = models.TextField(null=True, blank=True)

    sensitive = models.BooleanField(null=True, blank=True)
    spoiler_text = models.TextField(null=True, blank=True)
    visibility = models.TextField()
    language = models.TextField(null=True, blank=True)
    uri = models.URLField()
    url = models.URLField()
    replies_count = models.IntegerField()
    reblogs_count = models.IntegerField()
    favourites_count = models.IntegerField()
    edited_at = models.DateTimeField(null=True, blank=True)
    content = models.TextField()
    reblog = models.TextField(null=True, blank=True)
    application = models.JSONField(null=True, blank=True)
    media_attachments = models.JSONField(default=list)
    mentions = models.JSONField(default=list)
    tags = models.JSONField(default=list)
    emojis = models.JSONField(default=list)
    card = models.JSONField(null=True, blank=True)
    poll = models.JSONField(null=True, blank=True)

    class Meta:
        unique_together = ("post_id", "instance")
        constraints = [models.UniqueConstraint(fields=["url"], name="unique_post_dotnetcon_url")]
