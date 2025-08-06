from django.contrib import admin

from starter_packs.models import StarterPack


@admin.register(StarterPack)
class AuthorAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "slug",
        "description",
        "created_at",
        "updated_at",
        "created_by_id",
        "deleted_at",
        "published_at",
        "splash_image",
        "daily_follows",
        "monthly_follows",
        "weekly_follows",
    )
    search_fields = (
        "title",
        "slug",
    )
