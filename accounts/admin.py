from django.contrib import admin
from django.contrib.auth.models import User

from accounts.models import Account

admin.site.unregister(User)


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
        return obj.note
