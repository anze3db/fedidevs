from django.db import models


class Announcement(models.Model):
    """A single fediverse post the @fedidevs account should publish.

    The model only knows what it takes to make (and track) a Mastodon post: the
    text, the visibility, when it is due, and the result. It has no idea what the
    post is *about* — callers (e.g. confs) create rows and hold references to
    them. Posting is done by the ``postannouncements`` management command.
    """

    class Visibility(models.TextChoices):
        PUBLIC = "public", "Public"
        UNLISTED = "unlisted", "Unlisted"
        PRIVATE = "private", "Followers only"
        DIRECT = "direct", "Direct"

    content = models.TextField(help_text="The status text to post.")
    visibility = models.CharField(max_length=10, choices=Visibility.choices, default=Visibility.PUBLIC)

    post_at = models.DateTimeField(help_text="When this announcement is due, in UTC.")

    posted_at = models.DateTimeField(null=True, blank=True, help_text="Set when the post succeeded.")
    post_url = models.URLField(default="", blank=True, help_text="Link to the published fediverse post.")
    error = models.TextField(default="", blank=True, help_text="Last posting error, if any.")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["posted_at", "post_at"])]

    def __str__(self):
        return f"Announcement #{self.pk} due {self.post_at:%Y-%m-%d %H:%M}"
