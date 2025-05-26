from datetime import datetime

from django.conf import settings
from django.db.models import Count, Prefetch
from django.urls import reverse
from ninja import Field, Router, Schema
from ninja.pagination import paginate
from zeal import zeal_ignore

from starter_packs.models import StarterPack


class AccountSchema(Schema):
    id: str = Field(..., alias="account.account_id")
    username: str = Field(..., alias="account.username")
    acct: str = Field(..., alias="account.acct")
    locked: bool = Field(..., alias="account.locked")
    bot: bool = Field(..., alias="account.bot")
    discoverable: bool | None = Field(..., alias="account.discoverable")
    # indexable: bool = Field(..., alias="account.indexable")
    group: bool | None = Field(..., alias="account.group")
    created_at: datetime = Field(..., alias="account.created_at")
    note: str = Field(..., alias="account.note")
    url: str = Field(..., alias="account.url")
    # uri: str = Field(..., alias="account.uri")
    avatar: str = Field(..., alias="account.avatar")
    avatar_static: str = Field(..., alias="account.avatar_static")
    header: str = Field(..., alias="account.header")
    header_static: str = Field(..., alias="account.header_static")
    followers_count: int = Field(..., alias="account.followers_count")
    following_count: int = Field(..., alias="account.following_count")
    statuses_count: int = Field(..., alias="account.statuses_count")
    last_status_at: datetime | None = Field(None, alias="account.last_status_at")
    display_name: str = Field(..., alias="account.display_name")
    fields: list[dict] = Field(..., alias="account.fields")
    emojis: list[dict] = Field(..., alias="account.emojis")
    # hide_collections: bool = Field(..., alias="account.hide_collections")
    noindex: bool | None = Field(..., alias="account.noindex")


class AuthUserSchema(Schema):
    id: str = Field(..., alias="accountaccess.account.account_id")
    username: str = Field(..., alias="accountaccess.account.username")
    acct: str = Field(..., alias="accountaccess.account.acct")
    locked: bool = Field(..., alias="accountaccess.account.locked")
    bot: bool = Field(..., alias="accountaccess.account.bot")
    discoverable: bool | None = Field(..., alias="accountaccess.account.discoverable")
    # indexable: bool = Field(..., alias="accountaccess.account.indexable")
    group: bool | None = Field(..., alias="accountaccess.account.group")
    created_at: datetime = Field(..., alias="accountaccess.account.created_at")
    note: str = Field(..., alias="accountaccess.account.note")
    url: str = Field(..., alias="accountaccess.account.url")
    # uri: str = Field(..., alias="accountaccess.account.uri")
    avatar: str = Field(..., alias="accountaccess.account.avatar")
    avatar_static: str = Field(..., alias="accountaccess.account.avatar_static")
    header: str = Field(..., alias="accountaccess.account.header")
    header_static: str = Field(..., alias="accountaccess.account.header_static")
    followers_count: int = Field(..., alias="accountaccess.account.followers_count")
    following_count: int = Field(..., alias="accountaccess.account.following_count")
    statuses_count: int = Field(..., alias="accountaccess.account.statuses_count")
    last_status_at: datetime | None = Field(None, alias="accountaccess.account.last_status_at")
    display_name: str = Field(..., alias="accountaccess.account.display_name")
    fields: list[dict] = Field(..., alias="accountaccess.account.fields")
    emojis: list[dict] = Field(..., alias="accountaccess.account.emojis")
    # hide_collections: bool = Field(..., alias="accountaccess.account.hide_collections")
    noindex: bool | None = Field(..., alias="accountaccess.account.noindex")


class StarterPackListSchema(Schema):
    slug: str = Field(...)
    description: str = Field(...)
    published_at: datetime = Field(...)
    updated_at: datetime | None = Field(None)
    created_by: AuthUserSchema = Field(..., alias="account")
    url: str
    html_url: str

    @staticmethod
    def resolve_url(starter_pack: StarterPack):
        return settings.ROOT_URL + reverse("api-1.0.0:starter_pack", kwargs={"starter_pack_slug": starter_pack.slug})

    @staticmethod
    def resolve_html_url(starter_pack: StarterPack):
        return settings.ROOT_URL + reverse("share_starter_pack", kwargs={"starter_pack_slug": starter_pack.slug})


class StarterPackSchema(StarterPackListSchema):
    items: list[AccountSchema]


router = Router()


@router.get("/", response=list[StarterPackListSchema], url_name="start_pack_list")
@paginate
def list_starter_packs(request):
    with zeal_ignore():
        return list(
            StarterPack.objects.filter(deleted_at=None, published_at__isnull=False)
            .order_by("-id")
            .prefetch_related(
                Prefetch("created_by", to_attr="account"),
                "account__accountaccess",
                "account__accountaccess__account",
                "account__accountaccess__account__instance_model",
                Prefetch("starterpackaccount_set", to_attr="items"),
                "items__account",
                "items__account__instance_model",
            )
        )


@router.get("/{starter_pack_slug}/", response=StarterPackSchema, url_name="starter_pack")
def get_starter_pack(request, starter_pack_slug: str):
    with zeal_ignore():
        sp = (
            StarterPack.objects.filter(deleted_at=None)
            .annotate(total_items=Count("starterpackaccount"))
            .prefetch_related(
                Prefetch("created_by", to_attr="account"),
                "account__accountaccess",
                "account__accountaccess__account",
                "account__accountaccess__account__instance_model",
                Prefetch("starterpackaccount_set", to_attr="items"),
                "items__account",
                "items__account__instance_model",
            )
            .get(slug=starter_pack_slug)
        )
    return sp
