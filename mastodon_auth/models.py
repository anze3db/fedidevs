from django.contrib.auth.models import User
from django.db import models

from accounts.misskey_api import is_misskey_family


class Instance(models.Model):
    url = models.CharField(max_length=255)
    client_id = models.CharField(max_length=255)
    client_secret = models.CharField(max_length=255)
    # Space-separated OAuth scopes the stored app was registered with. Empty for
    # legacy rows, which triggers re-registration on next login (see
    # mastodon_auth.views.login). Unused for Misskey-family (MiAuth) instances.
    scopes = models.CharField(max_length=255, default="")
    # nodeinfo software.name (e.g. "sharkey", "misskey"); empty means Mastodon /
    # Mastodon-compatible (the default OAuth path). Misskey-family instances use
    # MiAuth + the native API instead.
    software = models.CharField(max_length=64, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.url

    @property
    def is_misskey(self) -> bool:
        return is_misskey_family(self.software)

    class Meta:
        verbose_name = "Auth Instance"
        verbose_name_plural = "Auth Instance"


class AccountAccess(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    account = models.ForeignKey("accounts.Account", on_delete=models.CASCADE)
    instance = models.ForeignKey(Instance, on_delete=models.CASCADE)
    # TextField (not CharField(255)): Pixelfed / Laravel Passport issue JWT
    # access tokens that are ~700+ chars, well over the old 255 limit.
    access_token = models.TextField()
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
