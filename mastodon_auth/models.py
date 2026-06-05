from django.contrib.auth.models import User
from django.db import models


class Instance(models.Model):
    url = models.CharField(max_length=255)
    client_id = models.CharField(max_length=255)
    client_secret = models.CharField(max_length=255)
    # Space-separated OAuth scopes the stored app was registered with. Empty for
    # legacy rows, which triggers re-registration on next login (see
    # mastodon_auth.views.login).
    scopes = models.CharField(max_length=255, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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
    url = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("account", "url")
