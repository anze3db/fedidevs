from django.contrib import admin
from django.utils import timezone

from confs.models import Conference, ConferenceLookup, ConferenceTag


@admin.register(ConferenceTag)
class ConferenceTagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "icon")
    prepopulated_fields = {"slug": ("name",)}


class ConferenceLookupInline(admin.StackedInline):
    verbose_name = "Language or framework"
    verbose_name_plural = "Conference languages or frameworks"
    min_num = 1
    extra = 0
    model = ConferenceLookup


# Register your models here.
@admin.register(Conference)
class ConferenceAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "start_date", "end_date", "approved_at", "created_by", "archived_date")
    list_filter = ("approved_at",)
    actions = ["approve_conferences"]
    prepopulated_fields = {"slug": ("name",)}
    fields = (
        "name",
        "slug",
        "location",
        "time_zone",
        "start_date",
        "end_date",
        "approved_at",
        "created_by",
        "archived_date",
        "website",
        "mastodon",
        "description",
        "instances",
        "tags",
        "conference_tags",
        "days",
        "day_styles",
        "start_announcement",
        "end_announcement",
    )
    filter_horizontal = ("conference_tags",)
    raw_id_fields = ("start_announcement", "end_announcement", "created_by")
    # inlines = [ConferenceLookupInline]

    @admin.action(description="Approve selected conferences")
    def approve_conferences(self, request, queryset):
        updated = queryset.filter(approved_at__isnull=True).update(approved_at=timezone.now())
        self.message_user(request, f"Approved {updated} conference(s).")
