from django.contrib import admin

from confs.models import Conference, ConferenceLookup


class ConferenceLookupInline(admin.StackedInline):
    verbose_name = "Language or framework"
    verbose_name_plural = "Conference languages or frameworks"
    min_num = 1
    extra = 0
    model = ConferenceLookup


# Register your models here.
class ConferenceAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "start_date", "end_date", "archived_date", "posts_after")
    prepopulated_fields = {"slug": ("name",)}
    fields = (
        "name",
        "slug",
        "location",
        "time_zone",
        "start_date",
        "end_date",
        "archived_date",
        "website",
        "mastodon",
        "description",
        "instances",
        "tags",
        "days",
        "day_styles",
    )
    # inlines = [ConferenceLookupInline]


admin.site.register(Conference, ConferenceAdmin)
