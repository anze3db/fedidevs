from django.db import models


class StarterPack(models.Model):
    title = models.TextField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = models.TextField()

    created_by = models.ForeignKey("auth.User", on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    daily_follows = models.IntegerField(default=0)
    weekly_follows = models.IntegerField(default=0)
    monthly_follows = models.IntegerField(default=0)

    class Meta:
        unique_together = ("created_by", "slug")


class StarterPackAccount(models.Model):
    starter_pack = models.ForeignKey(StarterPack, on_delete=models.CASCADE)
    account = models.ForeignKey("accounts.Account", on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey("auth.User", on_delete=models.CASCADE)

    class Meta:
        unique_together = ("starter_pack", "account")
