from django.contrib.auth.models import User
from django.db import models


class Instance(models.Model):
    url = models.CharField(max_length=255)
    client_id = models.CharField(max_length=255)
    client_secret = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    scopes = models.JSONField(
        default=[
            "read:accounts",
            "read:blocks",
            "read:favourites",
            "read:filters",
            "read:follows",
            "read:lists",
            "read:mutes",
            "read:notifications",
            "read:search",
            "read:statuses",
            "read:bookmarks",
            "write:accounts",
            "write:blocks",
            "write:favourites",
            "write:filters",
            "write:follows",
            "write:lists",
            "write:media",
            "write:mutes",
            "write:notifications",
            "write:reports",
            "write:statuses",
            "write:bookmarks",
        ]
    )

    def __str__(self):
        return self.url

    class Meta:
        verbose_name = "Auth Instance"
        verbose_name_plural = "Auth Instance"


class AccountAccess(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    account = models.ForeignKey("accounts.Account", on_delete=models.CASCADE)
    instance = models.ForeignKey(Instance, on_delete=models.CASCADE)
    access_token = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.username


class AccountFollowing(models.Model):
    account = models.ForeignKey("accounts.Account", on_delete=models.CASCADE)
    url = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("account", "url")
