from django.db import models


# Create your models here.
class Post(models.Model):
    post_id = models.TextField()
    account = models.ForeignKey("accounts.Account", on_delete=models.CASCADE)
    instance = models.TextField()

    created_at = models.DateTimeField()
    in_reply_to_id = models.TextField(null=True, blank=True)
    in_reply_to_account_id = models.TextField(null=True, blank=True)

    senstive = models.BooleanField(null=True, blank=True)
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
