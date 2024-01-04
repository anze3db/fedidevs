from django.contrib import admin

from confs.models import Conference


# Register your models here.
class ConferenceAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "start_date", "end_date")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("accounts", "posts")


admin.site.register(Conference, ConferenceAdmin)
