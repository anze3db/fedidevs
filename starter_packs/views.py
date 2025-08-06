import hashlib
import io
import logging
import math
import random
import re

import dramatiq
import httpx
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.postgres.search import SearchQuery
from django.core.paginator import Paginator
from django.db import IntegrityError, models, transaction
from django.db.models import Exists, OuterRef, Q
from django.http import HttpResponse, HttpResponseServerError, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import gettext as _
from mastodon import (
    Mastodon,
    MastodonAPIError,
    MastodonInternalServerError,
    MastodonNotFoundError,
    MastodonServiceUnavailableError,
    MastodonUnauthorizedError,
    MastodonVersionError,
)
from PIL import Image, ImageDraw, ImageFilter, ImageFont, UnidentifiedImageError

from accounts.management.commands.crawlone import crawlone
from accounts.models import Account, Instance
from mastodon_auth.models import AccountFollowing
from starter_packs.models import StarterPack, StarterPackAccount
from stats.models import FollowAllClick

logger = logging.getLogger(__name__)
username_regex = re.compile(r"@?\b([\w0-9._%+-]+)@([\w0-9.-]+\.[\w]{2,})\b", re.IGNORECASE | re.UNICODE)


def starter_packs(request):
    tab = request.GET.get("tab")
    if tab not in ("community", "your", "containing"):
        tab = "community"

    order_by = request.GET.get("order_by", "latest")
    if order_by not in ("popular_day", "popular_week", "popular_month", "latest", "oldest"):
        order_by = "latest"

    # Map the order_by parameter to actual database fields
    order_by_mapping = {
        "latest": ["-created_at"],
        "oldest": ["created_at"],
        "popular_day": ["-daily_follows", "-created_at"],
        "popular_week": ["-weekly_follows", "-created_at"],
        "popular_month": ["-monthly_follows", "-created_at"],
    }
    db_order_by = order_by_mapping[order_by]

    starter_packs = StarterPack.objects.none()
    if tab == "community":
        starter_packs = StarterPack.objects.filter(published_at__isnull=False)
    elif tab == "your" and not request.user.is_anonymous:
        starter_packs = StarterPack.objects.filter(created_by=request.user)
    elif tab == "containing" and not request.user.is_anonymous:
        starter_packs = StarterPack.objects.filter(
            id__in=StarterPackAccount.objects.filter(account=request.user.accountaccess.account).values(
                "starter_pack_id"
            )
        )
    elif tab == "containing" and request.GET.get("username"):
        username = request.GET.get("username").lower()
        if username[0] != "@":
            username = "@" + username
        starter_packs = StarterPack.objects.filter(
            id__in=StarterPackAccount.objects.filter(account__username_at_instance=username).values("starter_pack_id")
        )

    starter_packs = (
        starter_packs.filter(
            deleted_at__isnull=True,
        )
        .annotate(
            num_accounts=models.Count(
                "starterpackaccount", filter=models.Q(starterpackaccount__account__discoverable=True)
            )
        )
        .order_by(*db_order_by)
        .prefetch_related("created_by__accountaccess__account")
    )

    if q := request.GET.get("q"):
        starter_packs = starter_packs.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(created_by__username__icontains=q)
            | Q(created_by__accountaccess__account__display_name__icontains=q)
        )

    paginator = Paginator(starter_packs, 100)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "starter_packs.html",
        {
            "page": "starter_packs",
            "page_url": reverse("starter_packs"),
            "page_title": _("Mastodon Starter Pack Directory | Fedidevs"),
            "page_description": _(
                "Discover, create, and share Mastodon starter packs to help new users find interesting accounts to follow."
            ),
            "page_header": "FEDIDEVS",
            "page_image": "og-starterpacks.png",
            "page_subheader": "",
            "starter_packs": page_obj,
            "containing_username": request.GET.get("username", ""),
        },
    )


class StarterPackForm(forms.ModelForm):
    class Meta:
        model = StarterPack
        fields = ["title", "description"]


@login_required
def add_accounts_to_starter_pack(request, starter_pack_slug):
    starter_pack = get_object_or_404(
        StarterPack, slug=starter_pack_slug, created_by=request.user, deleted_at__isnull=True
    )
    accounts = (
        Account.objects.filter()
        .prefetch_related("instance_model")
        .annotate(
            in_starter_pack=Exists(
                StarterPackAccount.objects.filter(
                    starter_pack=starter_pack,
                    account_id=OuterRef("pk"),
                )
            ),
            is_followed=Exists(
                AccountFollowing.objects.filter(account=request.user.accountaccess.account, url=OuterRef("url")),
            ),
        )
        .order_by("-is_followed", "-followers_count")
    )
    is_username = False
    if q := request.GET.get("q", ""):
        search = q.strip().lower()
        if search[0] != "@":
            search = "@" + search
        if username_regex.match(search):
            logger.info("Searching for username %s", search)
            is_username = True
            accounts = accounts.filter(
                username_at_instance=search,
                discoverable=True,
                noindex=False,
                instance_model__isnull=False,
                instance_model__deleted_at__isnull=True,
            )
            if not accounts.exists():
                logger.info("Username not found, crawling the instance")
                instance_name = search.split("@")[2]
                if Instance.objects.filter(instance=instance_name, deleted_at__isnull=False).exists():
                    logger.info("Instance is deleted")
                    return render(
                        request,
                        "add_accounts.html",
                        {
                            "page": "starter_packs",
                            "page_title": _("Add accounts to your starter pack"),
                            "page_description": "Add accounts to your starter pack to help new users find interesting accounts to follow.",
                            "page_header": "FEDIDEVS",
                            "page_subheader": "",
                            "q": q,
                            "is_username": is_username,
                            "num_accounts": StarterPackAccount.objects.filter(
                                account__discoverable=True, starter_pack=starter_pack
                            ).count(),
                            "accounts": accounts,
                            "starter_pack": starter_pack,
                            "deleted_instance": instance_name,
                        },
                    )
                account = crawlone(user=search[1:])
                if account:
                    accounts = Account.objects.filter(
                        username_at_instance=account.username_at_instance,
                    )
        else:
            logger.info("Using full text search for %s", search)
            accounts = accounts.filter(
                search=SearchQuery(search, search_type="websearch"),
                instance_model__isnull=False,
                instance_model__deleted_at__isnull=True,
            )

    paginator = Paginator(accounts.order_by("-followers_count"), 50)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "add_accounts_list.html" if "HX-Request" in request.headers else "add_accounts.html",
        {
            "page": "starter_packs",
            "page_title": _("Add accounts to your starter pack"),
            "page_description": "Add accounts to your starter pack to help new users find interesting accounts to follow.",
            "page_header": "FEDIDEVS",
            "page_subheader": "",
            "q": q,
            "is_username": is_username,
            "num_accounts": StarterPackAccount.objects.filter(
                account__discoverable=True, starter_pack=starter_pack
            ).count(),
            "accounts": page_obj,
            "starter_pack": starter_pack,
        },
    )


@login_required
def review_starter_pack(request, starter_pack_slug):
    starter_pack = get_object_or_404(
        StarterPack, slug=starter_pack_slug, created_by=request.user, deleted_at__isnull=True
    )
    accounts = (
        Account.objects.filter()
        .prefetch_related("instance_model")
        .annotate(
            in_starter_pack=Exists(
                StarterPackAccount.objects.filter(
                    starter_pack=starter_pack,
                    account_id=OuterRef("pk"),
                )
            ),
            is_followed=Exists(
                AccountFollowing.objects.filter(account=request.user.accountaccess.account, url=OuterRef("url")),
            ),
        )
        .filter(in_starter_pack=True, instance_model__isnull=False, instance_model__deleted_at__isnull=True)
        .order_by("-is_followed", "-followers_count")
    )

    paginator = Paginator(accounts, 50)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "review_starter_pack_list.html" if "HX-Request" in request.headers else "review_starter_pack.html",
        {
            "page": "starter_packs",
            "page_title": _("Review your starter pack"),
            "page_description": _("Review your starter pack to make sure everything is in order."),
            "page_header": "FEDIDEVS",
            "page_subheader": "",
            "review": True,
            "num_accounts": StarterPackAccount.objects.filter(
                account__discoverable=True, starter_pack=starter_pack
            ).count(),
            "accounts": page_obj,
            "starter_pack": starter_pack,
        },
    )


@login_required
def edit_starter_pack(request, starter_pack_slug):
    starter_pack = get_object_or_404(
        StarterPack, slug=starter_pack_slug, created_by=request.user, deleted_at__isnull=True
    )
    if request.method == "POST":
        form = StarterPackForm(request.POST, instance=starter_pack)
        if form.is_valid():
            form.save()
            return redirect("edit_accounts_starter_pack", starter_pack_slug=starter_pack.slug)
    else:
        form = StarterPackForm(instance=starter_pack)

    return render(
        request,
        "create_starter_pack.html",
        {
            "page": "starter_packs",
            "page_title": _("Edit your starter pack"),
            "page_description": _("Edit your starter pack to help new users find interesting accounts to follow."),
            "page_header": "FEDIDEVS",
            "page_subheader": "",
            "form": form,
            "starter_pack": starter_pack,
        },
    )


@login_required
def create_starter_pack(request):
    if request.method == "POST":
        form = StarterPackForm(request.POST)
        if form.is_valid():
            starter_pack = form.save(commit=False)
            starter_pack.created_by = request.user
            starter_pack.save()
            starter_pack.slug = urlsafe_base64_encode(str(starter_pack.id).encode())
            starter_pack.save(update_fields=["slug"])
            if get_splash_image_signature(starter_pack) != starter_pack.splash_image_signature:
                starter_pack.splash_image_needs_update = True
                starter_pack.save(update_fields=["splash_image_needs_update"])
            try:
                starter_pack.save()
                return redirect("edit_accounts_starter_pack", starter_pack_slug=starter_pack.slug)
            except IntegrityError:
                form.add_error(
                    "title",
                    forms.ValidationError(_("You already have a starter pack with this title.")),
                )
    else:
        form = StarterPackForm()

    return render(
        request,
        "create_starter_pack.html",
        {
            "page": "starter_packs",
            "page_title": _("Create a new starter pack"),
            "page_description": _("Create a new starter pack to help new users find interesting accounts to follow."),
            "page_header": "FEDIDEVS",
            "page_subheader": "",
            "form": form,
        },
    )


@transaction.atomic
def publish_starter_pack(request, starter_pack_slug):
    starter_pack = get_object_or_404(StarterPack, slug=starter_pack_slug, created_by=request.user)
    if request.method == "POST":
        if starter_pack.published_at:
            starter_pack.published_at = None
            starter_pack.splash_image_needs_update = False
        else:
            starter_pack.published_at = timezone.now()
            if get_splash_image_signature(starter_pack) != starter_pack.splash_image_signature:
                starter_pack.splash_image_needs_update = True
        starter_pack.save(update_fields=["published_at", "updated_at", "splash_image_needs_update"])

    response = HttpResponse()
    response["HX-Redirect"] = reverse("share_starter_pack", kwargs={"starter_pack_slug": starter_pack.slug})
    return response


@transaction.atomic
def toggle_account_to_starter_pack(request, starter_pack_slug, account_id):
    starter_pack = get_object_or_404(
        StarterPack, slug=starter_pack_slug, deleted_at__isnull=True, created_by=request.user
    )
    account = get_object_or_404(Account, id=account_id)
    if StarterPackAccount.objects.filter(starter_pack=starter_pack, account_id=account_id).exists():
        StarterPackAccount.objects.filter(
            starter_pack=starter_pack,
            account_id=account_id,
        ).delete()
    else:
        if StarterPackAccount.objects.filter(starter_pack=starter_pack).count() >= 150:
            return render(
                request,
                "starter_pack_stats.html",
                {
                    "starter_pack": starter_pack,
                    "num_accounts": StarterPackAccount.objects.filter(starter_pack=starter_pack).count(),
                    "error": _("You have reached the maximum number of accounts in a starter pack."),
                },
            )
        if not account.can_add_to_starter_pack:
            return render(
                request,
                "starter_pack_stats.html",
                {
                    "starter_pack": starter_pack,
                    "num_accounts": StarterPackAccount.objects.filter(starter_pack=starter_pack).count(),
                    "error": _("The account cannot be added to the starter pack due to privacy settings."),
                },
            )
        StarterPackAccount.objects.create(
            starter_pack=starter_pack,
            account_id=account_id,
            created_by=request.user,
        )
    if (
        get_splash_image_signature(starter_pack) != starter_pack.splash_image_signature
        and starter_pack.published_at is not None
    ):
        starter_pack.splash_image_needs_update = True
        starter_pack.save(update_fields=["splash_image_needs_update"])

    return render(
        request,
        "starter_pack_stats.html",
        {
            "starter_pack": starter_pack,
            "review": request.POST.get("review"),
            "num_accounts": StarterPackAccount.objects.filter(starter_pack=starter_pack).count(),
        },
    )


def get_preferred_format(request):
    # Check which one of the data formats we can supply (HTML, JSON, ActivityPub)
    # best matches the client's request. There may be a `format` query parameter
    # asking for a specific one. If there isn't, we use HTTP content negotiation
    # to react to the client's `Accept` header. If after that there is still no
    # clear preference, we default to HTML.
    # See also: https://www.w3.org/TR/activitypub/#retrieving-objects

    if request.GET.get("format") in ["activitypub", "json", "html"]:
        return request.GET["format"]

    # Order matters here: If the request has no `Accept` header at all, the function
    # `get_preferred_type` will return the first type instead of `None`. So as our
    # fallback format, `text/html` must be listed first.
    available_types = [
        "text/html",
        "application/json",
        'application/ld+json; profile="https://www.w3.org/ns/activitystreams"',
        "application/activity+json",
    ]
    preferred_type = request.get_preferred_type(available_types)
    result = "text/html"  # Default
    if preferred_type in [
        'application/ld+json; profile="https://www.w3.org/ns/activitystreams"',
        "application/activity+json",
    ]:
        result = "activitypub"
    elif preferred_type == "application/json":
        result = "json"

    return result


def share_starter_pack(request, starter_pack_slug):
    starter_pack = get_object_or_404(StarterPack, slug=starter_pack_slug, deleted_at__isnull=True)
    accounts = (
        Account.objects.filter(
            starterpackaccount__starter_pack=starter_pack,
            instance_model__isnull=False,
            instance_model__deleted_at__isnull=True,
            discoverable=True,
        )
        .select_related("accountlookup", "instance_model")
        .order_by("-followers_count")
    )

    if get_preferred_format(request) == "json":
        data = {
            "url": request.build_absolute_uri(
                reverse("share_starter_pack", kwargs={"starter_pack_slug": starter_pack.slug})
            ),
            "title": starter_pack.title,
            "description": starter_pack.description,
            "created_by": starter_pack.created_by.username,
            "created_at": starter_pack.created_at,
            "updated_at": starter_pack.updated_at,
            "published_at": starter_pack.published_at,
            "daily_follows": starter_pack.daily_follows,
            "weekly_follows": starter_pack.weekly_follows,
            "monthly_follows": starter_pack.monthly_follows,
            "accounts": [
                {
                    "name": account.name,
                    "handle": account.username_at_instance,
                    "url": account.url,
                    "activitypub_id": account.activitypub_id,
                    "created_at": account.created_at,
                    "followers_count": account.followers_count,
                    "following_count": account.following_count,
                    "statuses_count": account.statuses_count,
                    "bot": account.bot,
                    "discoverable": account.discoverable,
                    "locked": account.locked,
                    "noindex": account.noindex,
                    "avatar": account.avatar,
                    "header": account.avatar,
                }
                for account in accounts
            ],
        }
        response = JsonResponse(data, status=200, content_type="application/json; charset=utf-8")
        return response
    elif get_preferred_format(request) == "activitypub":
        author = starter_pack.created_by.accountaccess.account
        if author.activitypub_id is None:
            # Owner of this starter pack does not have an ActivityPub ID stored yet.
            # This should be resolved somewhere else by a background task, so we
            # return an HTTP 500 error and leave it to the client to try again later.
            return HttpResponseServerError()
        items = [account.activitypub_id for account in accounts]
        if None in items:
            # One or more of the accounts in this starter pack do not have an
            # ActivityPub ID stored yet. Same consideration as above.
            return HttpResponseServerError()
        data = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "type": "Collection",
            "id": request.build_absolute_uri(
                reverse("share_starter_pack", kwargs={"starter_pack_slug": starter_pack.slug})
            ),
            "name": re.sub(r":\w+:", "", starter_pack.title).strip(),
            "summary": starter_pack.description,
            "attributedTo": author.activitypub_id,
            "published": starter_pack.created_at,
            "updated": starter_pack.updated_at,
            "image": {
                "type": "Image",
                "mediaType": "image/png",
                "url": request.build_absolute_uri("/static/og-starterpack.png"),
                # In The ActivityPub ecosystem, the `summary` property is commonly used for image
                # alt text (analogous to the HTML `alt` attribute). We want to emphasize for other
                # implementers and consumers that this is possible here. However, we supply an empty
                # string as our alt text because our starter pack splash images are presumed to be
                # “either decorative or supplemental to the rest of the content, redundant with
                # some other information in the document” (WHATWG HTML Living Standard on what it
                # means when the alt attribute is the empty string). That is, people who do not see
                # the image lose no information since the title and content of the starter pack are
                # right here in the same document.
                "summary": "",
            },
            "generator": {
                "type": "Application",
                "name": "Fedidevs",
                "url": request.build_absolute_uri("/"),
            },
            "totalItems": accounts.count(),
            "items": items,
        }
        response = JsonResponse(data, status=200, content_type="application/activity+json; charset=utf-8")
        return response

    if request.user.is_authenticated:
        # Annotate whether the current request user is following the account:
        accounts = accounts.annotate(
            is_following=Exists(
                AccountFollowing.objects.filter(account=request.user.accountaccess.account, url=OuterRef("url")),
            )
        )

    paginator = Paginator(accounts, 50)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "starter_pack_accounts.html" if "HX-Request" in request.headers else "share_starter_pack.html",
        {
            "page_title": re.sub(r":\w+:", "", starter_pack.title).strip() + _(" - Mastodon Starter Pack"),
            "page": "starter_packs",
            "page_url": reverse("share_starter_pack", kwargs={"starter_pack_slug": starter_pack_slug}),
            "page_header": "FEDIDEVS",
            "page_subheader": "",
            "page_image": "og-starterpack.png",
            "page_description": starter_pack.description,
            "starter_pack": starter_pack,
            "num_accounts": accounts.count(),
            "num_hidden_accounts": Account.objects.exclude(
                discoverable=True, instance_model__isnull=False, instance_model__deleted_at__isnull=True
            )
            .filter(starterpackaccount__starter_pack=starter_pack)
            .count(),
            "accounts": page_obj,
        },
    )


@login_required
def delete_starter_pack(request, starter_pack_slug):
    starter_pack = get_object_or_404(StarterPack, slug=starter_pack_slug, created_by=request.user)
    if request.method == "POST":
        starter_pack.deleted_at = timezone.now()
        starter_pack.save(update_fields=["deleted_at"])
    else:
        return render(
            request,
            "delete_starter_pack.html",
            {
                "page": "starter_packs",
                "starter_pack": starter_pack,
            },
        )

    return redirect("starter_packs")


def follow_starter_pack(request, starter_pack_slug):
    starter_pack = get_object_or_404(StarterPack, slug=starter_pack_slug, deleted_at__isnull=True)
    accounts = Account.objects.filter(
        starterpackaccount__starter_pack=starter_pack,
        instance_model__deleted_at__isnull=True,
    ).select_related("accountlookup", "instance_model")
    account_following = []
    for account in accounts:
        account_following.append(AccountFollowing(account=request.user.accountaccess.account, url=account.url))

    AccountFollowing.objects.bulk_create(account_following, ignore_conflicts=True)
    transaction.on_commit(lambda: follow_bg.send(request.user.id, starter_pack_slug))
    FollowAllClick.objects.create(user=request.user, starter_pack=starter_pack)
    messages.success(request, _("Following all accounts in the starter pack. 🎉"))

    return redirect("share_starter_pack", starter_pack_slug=starter_pack.slug)


@dramatiq.actor
def follow_bg(user_id: int, starter_pack_slug: str):
    user = User.objects.get(pk=user_id)
    account_access = user.accountaccess
    instance = account_access.instance
    mastodon = Mastodon(
        api_base_url=instance.url,
        client_id=instance.client_id,
        client_secret=instance.client_secret,
        access_token=account_access.access_token,
        user_agent="fedidevs",
    )

    starter_pack_accounts = Account.objects.filter(
        starterpackaccount__starter_pack__slug=starter_pack_slug,
        instance_model__deleted_at__isnull=True,
        discoverable=True,
    )

    for account in starter_pack_accounts:
        if account == account_access.account:
            # Skip self
            continue

        if account.instance == instance.url:
            account_id = account.account_id
        else:
            try:
                local_account = mastodon.account_lookup(acct=account.username_at_instance)
            except (MastodonNotFoundError, MastodonVersionError, MastodonInternalServerError):
                # Attempt to resolve through search:
                try:
                    local_accounts = mastodon.account_search(q=account.username_at_instance, resolve=True, limit=1)
                except MastodonServiceUnavailableError:
                    logger.exception("Service unavailable when searching for %s", account.username_at_instance)
                    continue
                except Exception:
                    logger.exception("Unknown error when searching for %s", account.username_at_instance)
                    continue
                if not local_accounts:
                    logger.exception("Account not found on instance %s", account.username_at_instance)
                    continue
                local_account = local_accounts[0]
                if local_account["acct"].lower() != account.username_at_instance[1:]:
                    logger.exception("Account mismatch %s %s", account.username_at_instance[1:], local_account["acct"])
                    continue
            except MastodonUnauthorizedError:
                logger.exception("Not authorized %s", account.username_at_instance)
                continue
            except MastodonAPIError:
                logger.exception("Unknown error when following %s", account.username_at_instance)
                continue
            account_id = local_account["id"]

        try:
            mastodon.account_follow(account_id)
        except MastodonUnauthorizedError:
            logger.exception("Unauthorized error when following")
            continue
        except MastodonAPIError:
            # We weren't able to follow the user. Maybe the account was moved?
            try:
                local_account = mastodon.account_lookup(acct=account.username_at_instance)
            except MastodonNotFoundError:
                logger.warning("Account not found on instance %s", account.username_at_instance)
                continue
            if moved := local_account.get("moved"):
                account.moved = moved
                account.save(update_fields=("moved",))
                logger.warning("Account %s moved", account.username_at_instance)
                continue

            logger.error("Unknown error when following %s", account.username_at_instance)
            continue


# The maximum number of avatars that will appear on a starter pack splash
# image, limited for the purposes of render time/traffic and aesthetics.
SPLASH_IMAGE_NUMBER_OF_AVATARS = 24


def get_splash_image_accounts(starter_pack):
    accounts = (
        Account.objects.filter(
            starterpackaccount__starter_pack=starter_pack,
            instance_model__isnull=False,
            instance_model__deleted_at__isnull=True,
            discoverable=True,
        )
        .select_related("accountlookup", "instance_model")
        .order_by("starterpackaccount__created_at")
    )
    return list(accounts[:SPLASH_IMAGE_NUMBER_OF_AVATARS])


def get_splash_image_signature(starter_pack):
    """
    Calculates a 32 character signature (checksum, hash) of the content in
    a given starter pack which would appear on the splash image. This is
    used to discern whether the splash image needs to be rerendered after
    a starter pack has been modified, or if the content is unchanged under
    the current render settings.
    """
    accounts = get_splash_image_accounts(starter_pack)
    accounts = [account.get_username_at_instance() for account in accounts]
    content = starter_pack.title + ",".join(sorted(accounts))
    return hashlib.sha512(content.encode("utf-8")).hexdigest()[:32]


def get_splash_background(width, height, attribution, font, cache_path):
    """
    Creates a PIL image according to the given `width` and `height`, fills it
    with a gradient background, and adds a site-specific `attribution` in the
    lower right corner using `font`.
    This function caches its result in `cache_path` and attempts to reuse it
    for successive images of the same dimensions.
    """
    if cache_path.is_file():
        try:
            return Image.open(cache_path)
        except UnidentifiedImageError:
            logger.warning("Cached splash image background for size (%d, %d) corrupted, rerendering", width, height)
            # Fall through into (re-)render code path

    background = Image.new("RGBA", (width, height))
    left_color = (255, 87, 87)
    right_color = (140, 82, 255)
    for x in range(width):
        progress = x / (width - 1)
        mixed_color = (
            round(progress * left_color[0] + (1 - progress) * right_color[0]),
            round(progress * left_color[1] + (1 - progress) * right_color[1]),
            round(progress * left_color[2] + (1 - progress) * right_color[2]),
            255,
        )
        background.paste(mixed_color, (x, 0, x + 1, height))

    draw = ImageDraw.Draw(background)
    font_size = font.getmetrics()[0] - font.getmetrics()[1]
    draw.text(
        (width - 0.6 * font_size, height - 0.3 * font_size), attribution, fill=(255, 255, 255), font=font, anchor="rb"
    )
    background.save(cache_path)
    return background


def fetch_avatar(url, crop_mask):
    """
    Fetches a remote avatar from a URL and returns it as PIL image resized to
    the dimensions of `mask` and with `mask` applied as an alpha mask size in
    pixels (same width and height). If the avatar is non-square, it is squished.
    If it contains transparency, a gray background is applied before `crop`mask.

    Returns `None` if the download fails, the avatar is too large (in bytes or
    in resolution), or pretty much anything else goes wrong.
    """

    max_bytes = 8 * 1024 * 1024
    client = httpx.Client()
    avatar_bytes = io.BytesIO()

    try:
        with httpx.stream("GET", url, follow_redirects=True) as response:
            if response.status_code != 200:
                return None
            size_bytes = int(response.headers.get("Content-Length", "0"))
            if size_bytes > max_bytes:
                return None
            for chunk in response.iter_bytes():
                if response.num_bytes_downloaded > max_bytes:
                    return None
                avatar_bytes.write(chunk)
    except (httpx.HTTPError, httpx.InvalidURL):
        return None
    finally:
        client.close()

    original_max_image_pixels = Image.MAX_IMAGE_PIXELS
    try:
        Image.MAX_IMAGE_PIXELS = 4000 * 4000
        avatar = Image.open(avatar_bytes)
    except (Image.DecompressionBombError, UnidentifiedImageError):
        return None
    finally:
        Image.MAX_IMAGE_PIXELS = original_max_image_pixels

    avatar = avatar.convert("RGBA")
    avatar = avatar.resize((crop_mask.width, crop_mask.height), resample=Image.Resampling.LANCZOS)
    modified = Image.new("RGBA", (crop_mask.width, crop_mask.height), (127, 127, 127, 255))
    modified.alpha_composite(avatar)
    modified.putalpha(crop_mask)
    return modified


def render_splash_image(starter_pack, host_attribution):
    """
    Renders (or re-renders) a splash image for a specific starter pack.
    The result is returned as a PIL image and stored in the media
    directory. Note that this triggers a download of up to
    `SPLASH_IMAGE_NUMBER_OF_AVATARS` remote avatars and a good amount
    of CPU and RAM use -- this operation is _expensive_! The caller is
    responsible for sensible scheduling.

    Note: `host_attribution` is cached eagerly by the background gradient
    renderer. The value is only used if no background for the configured
    render size is in the local cache.
    """

    resolution = (1200, 630)  # final rendered image size in pixels
    supersampling_factor = 3  # scaling factor for render canvas size (to avoid aliasing)
    media_dir = settings.BASE_DIR / "media"
    splash_dir = settings.BASE_DIR / "media" / "splash"

    for directory in (media_dir, splash_dir):
        try:
            directory.mkdir(mode=0o770, exist_ok=True)
        except (FileExistsError, PermissionError) as e:
            # With `exist_ok=True`, the FileExistsError is only raised if the media path
            # already exists and is _not_ a directory.
            logger.exception("Unable to create %s directory: %s", directory, type(e).__name__)
            return
        try:
            write_test_path = directory / "__write_test.lock"
            write_test_path.touch()
            write_test_path.unlink()
        except OSError:
            logger.exception("Unable to write to directory %s", directory)
            return

    render_resolution = (resolution[0] * supersampling_factor, resolution[1] * supersampling_factor)
    font_path = settings.BASE_DIR / "static" / "InterVariable.ttf"
    attribution_font = ImageFont.truetype(font_path, round(30 * supersampling_factor))

    image = get_splash_background(
        render_resolution[0],
        render_resolution[1],
        f"Hosted by {host_attribution}",
        attribution_font,
        media_dir / f"starterpack_bg_{render_resolution[0]}x{render_resolution[1]}.png",
    )

    margin_top = 2.5 * 48 * supersampling_factor
    margin_bottom = 2 * 36 * supersampling_factor
    margin_side = 0.05 * resolution[0] * supersampling_factor

    accounts = get_splash_image_accounts(starter_pack)
    random.shuffle(accounts)

    inner_width = render_resolution[0] - 2 * margin_side
    inner_height = render_resolution[1] - margin_top - margin_bottom
    inner_aspect_ratio = inner_width / inner_height

    num_lines = 1 + math.floor(math.sqrt(max(len(accounts) - 1, 1) / inner_aspect_ratio))
    per_line = math.floor(len(accounts) / num_lines)
    num_lines = math.floor(len(accounts) / per_line)
    leftover = len(accounts) % per_line
    lines = []
    for _i in range(num_lines):
        lines.append(per_line)
    expand_line_count = 1
    while leftover > 0:
        for i in range(expand_line_count):
            lines[i + math.floor((num_lines - expand_line_count) / 2)] += 1
            leftover -= 1
            if leftover == 0:
                break
        expand_line_count = min(expand_line_count + 2, num_lines)
    for i in range(1, num_lines):
        if lines[i] < lines[i - 1] - 1:
            lines[i] += 1
            lines[i - 1] -= 1

    circle_distance = inner_width / max(lines)
    circle_distance = min(circle_distance, (inner_height / (1 + math.sin(math.pi / 3) * (len(lines) - 1))))
    # We separate `circle_radius` from `circle_distance` to
    # scale the circles' relative size in the future.
    circle_radius = circle_distance / 2
    outline_thickness = math.floor(0.09 * circle_distance / 2)
    avatar_size = round(circle_radius * 2)
    crop_mask = Image.new("L", (avatar_size, avatar_size), 0)
    crop_mask_draw = ImageDraw.Draw(crop_mask)
    crop_mask_draw.circle(
        (round(crop_mask.width / 2), round(crop_mask.height / 2)),
        round(crop_mask.width / 2),
        fill=255,
    )

    empty_avatar = Image.new("RGBA", (crop_mask.width, crop_mask.height), (0, 0, 0, 0))
    avatars = []
    for account in accounts:
        avatar = fetch_avatar(account.avatar, crop_mask)
        if avatar is not None:
            avatars.append(avatar)
        else:
            logger.warning("Failed to fetch avatar of account %s for splash image", account.get_username_at_instance())
            avatars.append(empty_avatar)

    min_x = 9999999
    min_y = 9999999
    max_x = -9999999
    max_y = -9999999
    line_start = 0
    avatar_positions = []
    for y in range(len(lines)):
        shift = -0.25 + (y % 2) * 0.5
        if y > 0:
            if lines[y] > lines[y - 1] and shift > 0:
                line_start -= 1
            elif lines[y] < lines[y - 1] and shift < 0:
                line_start += 1
        for x in range(lines[y]):
            cx = (line_start + x + shift) * circle_distance
            cy = (y - num_lines / 2) * circle_distance * math.sin(math.pi / 3)
            avatar_positions.append((cx, cy))
            min_x = min(cx, min_x)
            max_x = max(cx, max_x)
            min_y = min(cy, min_y)
            max_y = max(cy, max_y)

    diff_x = render_resolution[0] / 2 - (max_x + min_x) / 2
    diff_y = render_resolution[1] / 2 - (margin_bottom - margin_top) / 2 - (max_y + min_y) / 2

    shadow_layer = Image.new("RGBA", render_resolution, (0, 0, 0, 0))
    outline_layer = Image.new("RGBA", render_resolution, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    outline_draw = ImageDraw.Draw(outline_layer)

    title_font = ImageFont.truetype(font_path, 64)
    title_font.set_variation_by_name("Bold")
    title_width = title_font.getlength(starter_pack.title)
    title_max_width = 0.9 * resolution[0]  # 5% margin left and right
    title_font_size = round(min(1, title_max_width / title_width) * 64 * supersampling_factor)
    title_font = ImageFont.truetype(font_path, title_font_size)
    title_font.set_variation_by_name("Bold")

    i = 0
    for y in range(num_lines):
        for _x in range(lines[y]):
            pixel_x = round(avatar_positions[i][0] + diff_x - avatar_size / 2)
            pixel_y = round(avatar_positions[i][1] + diff_y - avatar_size / 2)
            image.alpha_composite(avatars[i], (pixel_x, pixel_y))
            for job in ((shadow_draw, (0, 0, 0, 63)), (outline_draw, (255, 255, 255, 255))):
                job[0].circle(
                    (avatar_positions[i][0] + diff_x, avatar_positions[i][1] + diff_y),
                    math.floor(circle_radius + outline_thickness / 2),
                    outline=job[1],
                    fill=None,
                    width=outline_thickness,
                )
                job[0].text(
                    (render_resolution[0] / 2, 48 * supersampling_factor),
                    starter_pack.title,
                    fill=job[1],
                    font=title_font,
                    anchor="mm",
                )
            i += 1

    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=3 * supersampling_factor))
    image.alpha_composite(shadow_layer)
    image.alpha_composite(outline_layer)

    image.convert("RGB")
    image = image.resize(resolution, resample=Image.Resampling.LANCZOS)
    image.save(splash_dir / (starter_pack.slug + ".png"))
    image.close()

    starter_pack.splash_image = f"splash/{starter_pack.slug}.png"
    starter_pack.splash_image_signature = get_splash_image_signature(starter_pack)
    starter_pack.splash_image_updated_at = timezone.now()
    starter_pack.splash_image_needs_update = False
    starter_pack.save(
        update_fields=["splash_image", "splash_image_signature", "splash_image_updated_at", "splash_image_needs_update"]
    )
