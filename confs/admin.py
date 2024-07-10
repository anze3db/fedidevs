from django.contrib import admin

from confs.models import Conference


# Register your models here.
class ConferenceAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "start_date", "end_date", "archived_date", "posts_after")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("accounts", "posts")
    fields = (
        "name",
        "slug",
        "location",
        "start_date",
        "end_date",
        "archived_date",
        "website",
        "mastodon",
        "description",
        "instances",
        "tags",
        "days",
    )


admin.site.register(Conference, ConferenceAdmin)
