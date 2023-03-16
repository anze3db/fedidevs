from django.db import models


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
