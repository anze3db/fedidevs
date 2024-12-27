from django.db import models


class Post(models.Model):
    post_id = models.TextField()
    account = models.ForeignKey("accounts.Account", on_delete=models.CASCADE)
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
        unique_together = (
            "post_id",
            "account",
        )
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["account", "created_at"]),
        ]


class DjangoConUS23Post(models.Model):
    post_id = models.TextField()
    account = models.JSONField()
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


class PostSubscription(models.Model):
    email = models.EmailField()
    framework_or_lang = models.TextField(null=True, blank=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)
