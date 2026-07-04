from django.contrib import admin

from announcements.models import Announcement


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("__str__", "visibility", "post_at", "posted_at", "post_url")
    list_filter = ("visibility", "posted_at")
    readonly_fields = ("posted_at", "post_url", "error", "created_at")
