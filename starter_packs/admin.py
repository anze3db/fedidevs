from django.contrib import admin

from starter_packs.models import StarterPack, StarterPackInvitation
from starter_packs.splash_images import render_splash_image


@admin.action(description="Update splash image for selected starter packs")
def update_splash_image(_modeladmin, request, queryset):
    for starter_pack in queryset:
        render_splash_image(starter_pack, request.get_host())


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
        "splash_image_signature",
        "splash_image_updated_at",
        "splash_image_needs_update",
        "daily_follows",
        "monthly_follows",
        "weekly_follows",
    )
    search_fields = (
        "title",
        "slug",
    )
    filter_horizontal = ("owners",)
    actions = [update_splash_image]


@admin.register(StarterPackInvitation)
class StarterPackInvitationAdmin(admin.ModelAdmin):
    list_display = ("id", "starter_pack", "invited_user", "invited_by", "created_at")
    raw_id_fields = ("starter_pack", "invited_user", "invited_by")
