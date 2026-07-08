from dataclasses import dataclass

from django.contrib.postgres.fields import ArrayField
from django.db import models

# Maximum number of owners (users with edit rights) a starter pack can have.
MAX_OWNERS = 10

# Maximum number of accounts that can be pinned to the top of a starter pack.
MAX_PINNED_ACCOUNTS = 10

# Maximum number of human languages a starter pack can be tagged with.
MAX_LANGUAGES = 5


@dataclass(frozen=True)
class PackLanguage:
    code: str  # ISO 639 / Django locale code
    name: str
    emoji: str


# The human languages a starter pack can be tagged with, each with a flag emoji for
# display. Curated (rather than Django's full ISO list) so every option carries a
# meaningful emoji. Kept alphabetical by name for the pickers.
PACK_LANGUAGES = [
    PackLanguage("ar", "Arabic", "🇸🇦"),
    PackLanguage("bn", "Bengali", "🇧🇩"),
    PackLanguage("zh-hans", "Chinese (Simplified)", "🇨🇳"),
    PackLanguage("zh-hant", "Chinese (Traditional)", "🇹🇼"),
    PackLanguage("cs", "Czech", "🇨🇿"),
    PackLanguage("da", "Danish", "🇩🇰"),
    PackLanguage("nl", "Dutch", "🇳🇱"),
    PackLanguage("en", "English", "🇬🇧"),
    PackLanguage("fi", "Finnish", "🇫🇮"),
    PackLanguage("fr", "French", "🇫🇷"),
    PackLanguage("de", "German", "🇩🇪"),
    PackLanguage("el", "Greek", "🇬🇷"),
    PackLanguage("he", "Hebrew", "🇮🇱"),
    PackLanguage("hi", "Hindi", "🇮🇳"),
    PackLanguage("hu", "Hungarian", "🇭🇺"),
    PackLanguage("id", "Indonesian", "🇮🇩"),
    PackLanguage("it", "Italian", "🇮🇹"),
    PackLanguage("ja", "Japanese", "🇯🇵"),
    PackLanguage("ko", "Korean", "🇰🇷"),
    PackLanguage("nb", "Norwegian", "🇳🇴"),
    PackLanguage("fa", "Persian", "🇮🇷"),
    PackLanguage("pl", "Polish", "🇵🇱"),
    PackLanguage("pt", "Portuguese", "🇵🇹"),
    PackLanguage("pt-br", "Portuguese (Brazil)", "🇧🇷"),
    PackLanguage("ro", "Romanian", "🇷🇴"),
    PackLanguage("ru", "Russian", "🇷🇺"),
    PackLanguage("sl", "Slovenian", "🇸🇮"),
    PackLanguage("es", "Spanish", "🇪🇸"),
    PackLanguage("sv", "Swedish", "🇸🇪"),
    PackLanguage("th", "Thai", "🇹🇭"),
    PackLanguage("tr", "Turkish", "🇹🇷"),
    PackLanguage("uk", "Ukrainian", "🇺🇦"),
    PackLanguage("vi", "Vietnamese", "🇻🇳"),
]

LANGUAGE_CHOICES = [(lang.code, lang.name) for lang in PACK_LANGUAGES]
LANGUAGES_BY_CODE = {lang.code: lang for lang in PACK_LANGUAGES}


class StarterPack(models.Model):
    title = models.TextField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = models.TextField()

    # Human languages this pack is tagged with (empty = unspecified), capped at
    # MAX_LANGUAGES by the form. Powers the language filter on the directory.
    languages = ArrayField(
        models.CharField(max_length=32, choices=LANGUAGE_CHOICES),
        blank=True,
        default=list,
    )

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

    @property
    def language_tags(self):
        """The pack's languages as PackLanguage objects (name + emoji), preserving
        saved order and skipping any codes no longer in PACK_LANGUAGES."""
        return [LANGUAGES_BY_CODE[code] for code in self.languages if code in LANGUAGES_BY_CODE]


class StarterPackAccount(models.Model):
    starter_pack = models.ForeignKey(StarterPack, on_delete=models.CASCADE)
    account = models.ForeignKey("accounts.Account", on_delete=models.CASCADE)

    # Pinned accounts are highlighted and listed at the top of the pack for all
    # viewers. Toggled by pack owners, capped at MAX_PINNED_ACCOUNTS per pack.
    pinned = models.BooleanField(default=False)

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
