from django.contrib import admin
from django.utils.html import mark_safe

from accounts.models import Account


@admin.register(Account)
class AuthorAdmin(admin.ModelAdmin):
    list_display = (
        "username",
        "display_name",
        "discoverable",
        "noindex",
        "followers_count",
        "following_count",
        "statuses_count",
        "bot",
        "locked",
        "last_sync_at",
        "html_note",
    )
    search_fields = (
        "username",
        "note",
    )

    def html_note(self, obj):
        return mark_safe(obj.note)
