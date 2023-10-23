from django.contrib import admin

from posts.models import DjangoConUS23Post, PostSubscription


# Register your models here.
@admin.register(DjangoConUS23Post)
class DjangoConUS23PostAdmin(admin.ModelAdmin):
    list_display = (
        "post_id",
        "instance",
        "created_at",
        "visibility",
        "language",
        "uri",
        "url",
        "replies_count",
        "reblogs_count",
        "favourites_count",
        "content",
    )
    list_filter = ("instance", "visibility", "language")
    search_fields = ("content",)


@admin.register(PostSubscription)
class PostSubscriptionsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "email",
        "framework_or_lang",
        "subscribed_at",
    )
    list_filter = ("subscribed_at",)
    search_fields = ("email",)
