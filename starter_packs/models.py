from django.db import models

# Maximum number of owners (users with edit rights) a starter pack can have.
MAX_OWNERS = 10


class StarterPack(models.Model):
    title = models.TextField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = models.TextField()

    # Original author, kept for attribution/display only (the "By X" line and the
    # JSON/ActivityPub author). NOT used for permission checks — those use `owners`.
    created_by = models.ForeignKey("auth.User", on_delete=models.CASCADE)
    # Users allowed to edit this pack. Seeded from created_by by migration; managed
    # via the owner UI (add/remove, capped at MAX_OWNERS, last owner can't leave).
    owners = models.ManyToManyField("auth.User", related_name="owned_starter_packs")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    splash_image = models.ImageField(upload_to="splash", blank=True, default="")
    splash_image_signature = models.CharField(blank=True, default="", max_length=32)
    splash_image_updated_at = models.DateTimeField(null=True)
    splash_image_needs_update = models.BooleanField(default=False)

    daily_follows = models.IntegerField(default=0)
    weekly_follows = models.IntegerField(default=0)
    monthly_follows = models.IntegerField(default=0)

    num_accounts = models.IntegerField(default=0)

    class Meta:
        unique_together = ("created_by", "slug")


class StarterPackAccount(models.Model):
    starter_pack = models.ForeignKey(StarterPack, on_delete=models.CASCADE)
    account = models.ForeignKey("accounts.Account", on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey("auth.User", on_delete=models.CASCADE)

    class Meta:
        unique_together = ("starter_pack", "account")


class StarterPackInvitation(models.Model):
    """A pending invitation for `invited_user` to become an owner of `starter_pack`.

    The row exists only while pending: accepting adds the user to `owners` and
    deletes the row; declining or cancelling deletes it.
    """

    starter_pack = models.ForeignKey(StarterPack, on_delete=models.CASCADE, related_name="invitations")
    invited_user = models.ForeignKey("auth.User", on_delete=models.CASCADE, related_name="starter_pack_invitations")
    invited_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("starter_pack", "invited_user")
