from django.db import models

# Create your models here.


class Conference(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    location = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    description = models.TextField()


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
