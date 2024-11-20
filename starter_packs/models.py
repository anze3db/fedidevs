from django.db import models


class StarterPack(models.Model):
    title = models.TextField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = models.TextField()

    created_by = models.ForeignKey("auth.User", on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("created_by", "slug")
