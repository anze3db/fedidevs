import logging
import re
from collections import defaultdict

from celery import shared_task
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.postgres.search import SearchQuery
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q
from django.http import HttpResponse, HttpResponseServerError, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from mastodon import (
    Mastodon,
)

from accounts.management.commands.crawlone import crawlone
from accounts.models import Account, Instance
from mastodon_auth.models import AccountAccess, AccountFollowing
from starter_packs.models import MAX_OWNERS, StarterPack, StarterPackAccount
from starter_packs.splash_images import get_splash_image_signature, render_splash_image
from starter_packs.utils import FollowError, resolve_and_follow_account, resolve_and_follow_misskey
from stats.models import FollowAllClick

logger = logging.getLogger(__name__)
username_regex = re.compile(r"^@?([\w0-9._%+-]+)@([\w0-9.-]+\.[\w]{2,})$", re.IGNORECASE | re.UNICODE)


def get_editable_pack(request, slug, **extra):
    """Fetch a starter pack the current user is allowed to edit (an owner), or 404.

    Permission is membership in `owners` — not `created_by`. Filtering the M2M by a
    single user yields at most one row (the through table is unique per pair).
    """
    return get_object_or_404(StarterPack, slug=slug, owners=request.user, **extra)


def pack_header_avatars(pack_ids, limit):
    """Map `starter_pack_id` -> up to `limit` `{avatar, handle, name}` dicts for the
    gradient headers (discoverable accounts on live instances). `handle`/`name`
    feed the per-avatar hover tooltip.

    One bounded query for all packs, grouped/capped in Python — avoids per-card
    N+1 and the ORM's lack of a clean "top N rows per group".
    """
    by_pack = defaultdict(list)
    if not pack_ids:
        return by_pack
    rows = (
        StarterPackAccount.objects.filter(
            starter_pack_id__in=pack_ids,
            account__discoverable=True,
            account__instance_model__isnull=False,
            account__instance_model__deleted_at__isnull=True,
        )
        .order_by("starter_pack_id", "created_at")
        .values_list(
            "starter_pack_id",
            "account__avatar_static",
            "account__username_at_instance",
            "account__display_name",
        )
    )
    for pack_id, avatar, handle, name in rows:
        if avatar and len(by_pack[pack_id]) < limit:
            by_pack[pack_id].append({"avatar": avatar, "handle": handle, "name": name})
    return by_pack


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
        # Packs you own (includes ones others added you to), not just ones you created.
        starter_packs = StarterPack.objects.filter(owners=request.user)
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
        .order_by(*db_order_by)
        .prefetch_related("created_by__accountaccess__account", "owners__accountaccess__account")
    )

    if q := request.GET.get("q", "").replace("\x00", "").strip():
        starter_packs = starter_packs.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(created_by__username__icontains=q)
            | Q(created_by__accountaccess__account__display_name__icontains=q)
        )

    paginator = Paginator(starter_packs, 30)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # A few account avatars per card for the gradient header (one query total).
    avatars = pack_header_avatars([pack.id for pack in page_obj], limit=6)
    for pack in page_obj:
        pack.header_avatars = avatars.get(pack.id, [])

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
            "page_image": static("og-starterpacks.png"),
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
    starter_pack = get_editable_pack(request, starter_pack_slug, deleted_at__isnull=True)
    try:
        access_account = request.user.accountaccess.account
    except AccountAccess.DoesNotExist:
        access_account = None
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
                AccountFollowing.objects.filter(account=access_account, url=OuterRef("url")),
            ),
        )
        .order_by("-is_followed", "-followers_count")
    )
    is_username = False
    if q := request.GET.get("q", "").replace("\x00", "").strip():
        search = q.lower()
        if search[0] != "@":
            search = "@" + search
        if username_regex.match(search):
            logger.info("Searching for username %s", search)
            is_username = True
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
                accounts = accounts.filter(
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
    starter_pack = get_editable_pack(request, starter_pack_slug, deleted_at__isnull=True)
    try:
        access_account = request.user.accountaccess.account
    except AccountAccess.DoesNotExist:
        access_account = None
    accounts = (
        Account.objects.prefetch_related("instance_model")
        .annotate(
            in_starter_pack=Exists(
                StarterPackAccount.objects.filter(
                    starter_pack=starter_pack,
                    account_id=OuterRef("pk"),
                )
            ),
            is_followed=Exists(
                AccountFollowing.objects.filter(account=access_account, url=OuterRef("url")),
            ),
        )
        .filter(
            starterpackaccount__starter_pack=starter_pack,
            in_starter_pack=True,
            instance_model__isnull=False,
            instance_model__deleted_at__isnull=True,
        )
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
    starter_pack = get_editable_pack(request, starter_pack_slug, deleted_at__isnull=True)
    if request.method == "POST":
        form = StarterPackForm(request.POST, instance=starter_pack)
        if form.is_valid():
            form.save()
            if (
                get_splash_image_signature(starter_pack) != starter_pack.splash_image_signature
                and starter_pack.published_at is not None
            ):
                starter_pack.splash_image_needs_update = True
                starter_pack.save(update_fields=["splash_image_needs_update"])
                transaction.on_commit(
                    lambda: update_starter_pack_splash_images.delay(starter_pack_slug=starter_pack.slug)
                )
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


def owners_manager_context(starter_pack, q="", owners_error=None):
    """Context for the owners management page/partial (owners_manager.html).

    `owners` is the current owner list; `search_results` are logged-in fedidevs
    users (those with an AccountAccess) matching `q`, excluding current owners.
    """
    owners = list(starter_pack.owners.select_related("accountaccess__account").order_by("username"))
    owner_ids = [owner.id for owner in owners]

    search_results = []
    if q:
        search_results = list(
            AccountAccess.objects.select_related("account")
            .filter(
                Q(account__username_at_instance__icontains=q)
                | Q(account__display_name__icontains=q)
                | Q(account__search=SearchQuery(q, search_type="websearch"))
            )
            .exclude(user_id__in=owner_ids)
            .order_by("-account__followers_count")[:20]
        )

    return {
        "starter_pack": starter_pack,
        "owners": owners,
        "owner_count": len(owners),
        "max_owners": MAX_OWNERS,
        "can_add": len(owners) < MAX_OWNERS,
        "search_results": search_results,
        "q": q,
        "owners_error": owners_error,
    }


@login_required
def manage_owners(request, starter_pack_slug):
    starter_pack = get_editable_pack(request, starter_pack_slug, deleted_at__isnull=True)
    q = request.GET.get("q", "").replace("\x00", "").strip()
    # On a live-search request, only the results region is swapped.
    if "HX-Request" in request.headers:
        return render(request, "owners_search_results.html", owners_manager_context(starter_pack, q))
    return render(
        request,
        "manage_owners.html",
        {
            "page": "starter_packs",
            "page_title": _("Manage owners"),
            "page_description": _("Add or remove people who can edit this starter pack."),
            "page_header": "FEDIDEVS",
            "page_subheader": "",
            **owners_manager_context(starter_pack, q),
        },
    )


@require_POST
@login_required
def add_owner(request, starter_pack_slug, user_id):
    starter_pack = get_editable_pack(request, starter_pack_slug, deleted_at__isnull=True)
    q = request.POST.get("q", "").replace("\x00", "").strip()
    error = None
    if not AccountAccess.objects.filter(user_id=user_id).exists():
        error = _("That person hasn't logged into Fedidevs yet, so they can't be added as an owner.")
    elif starter_pack.owners.filter(pk=user_id).exists():
        pass  # already an owner — no-op
    elif starter_pack.owners.count() >= MAX_OWNERS:
        error = _("This starter pack already has the maximum number of owners.")
    else:
        starter_pack.owners.add(user_id)

    return render(request, "owners_updated.html", owners_manager_context(starter_pack, q, error))


@require_POST
@login_required
def remove_owner(request, starter_pack_slug, user_id):
    starter_pack = get_editable_pack(request, starter_pack_slug, deleted_at__isnull=True)
    q = request.POST.get("q", "").replace("\x00", "").strip()
    if starter_pack.owners.count() <= 1:
        # The last owner can't be removed — a pack always has at least one editor.
        error = _("A starter pack must have at least one owner.")
        return render(request, "owners_updated.html", owners_manager_context(starter_pack, q, error))

    starter_pack.owners.remove(user_id)

    if user_id == request.user.id:
        # You removed yourself: you can no longer edit this pack, so leave the page.
        response = HttpResponse()
        response["HX-Redirect"] = "/"
        return response

    return render(request, "owners_updated.html", owners_manager_context(starter_pack, q))


@login_required
def create_starter_pack(request):
    if request.method == "POST":
        form = StarterPackForm(request.POST)
        if form.is_valid():
            starter_pack = form.save(commit=False)
            starter_pack.created_by = request.user
            starter_pack.save()
            starter_pack.owners.add(request.user)
            starter_pack.slug = urlsafe_base64_encode(str(starter_pack.id).encode())
            starter_pack.save(update_fields=["slug"])
            if get_splash_image_signature(starter_pack) != starter_pack.splash_image_signature:
                starter_pack.splash_image_needs_update = True
                starter_pack.save(update_fields=["splash_image_needs_update"])
                transaction.on_commit(
                    lambda: update_starter_pack_splash_images.delay(starter_pack_slug=starter_pack.slug)
                )
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
@login_required
def publish_starter_pack(request, starter_pack_slug):
    starter_pack = get_editable_pack(request, starter_pack_slug)
    if request.method == "POST":
        if starter_pack.published_at:
            starter_pack.published_at = None
            starter_pack.splash_image_needs_update = False
        else:
            starter_pack.published_at = timezone.now()
            if get_splash_image_signature(starter_pack) != starter_pack.splash_image_signature:
                starter_pack.splash_image_needs_update = True
                transaction.on_commit(
                    lambda: update_starter_pack_splash_images.delay(starter_pack_slug=starter_pack.slug)
                )
        starter_pack.save(update_fields=["published_at", "updated_at", "splash_image_needs_update"])

    response = HttpResponse()
    response["HX-Redirect"] = reverse("share_starter_pack", kwargs={"starter_pack_slug": starter_pack.slug})
    return response


@transaction.atomic
@login_required
def toggle_account_to_starter_pack(request, starter_pack_slug, account_id):
    # Check ownership first (M2M join), then take the row lock by pk — applying
    # SELECT ... FOR UPDATE across the owners join is not portable.
    editable = get_editable_pack(request, starter_pack_slug, deleted_at__isnull=True)
    starter_pack = get_object_or_404(StarterPack.objects.select_for_update(), pk=editable.pk)
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
    starter_pack.num_accounts = StarterPackAccount.objects.filter(
        starter_pack=starter_pack, account__discoverable=True
    ).count()
    starter_pack.save(update_fields=["num_accounts"])
    if (
        get_splash_image_signature(starter_pack) != starter_pack.splash_image_signature
        and starter_pack.published_at is not None
    ):
        starter_pack.splash_image_needs_update = True
        starter_pack.save(update_fields=["splash_image_needs_update"])
        transaction.on_commit(lambda: update_starter_pack_splash_images.delay(starter_pack_slug=starter_pack.slug))

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
        if starter_pack.splash_image:
            data["splash_image"] = request.build_absolute_uri(starter_pack.splash_image.url)
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
        if starter_pack.splash_image:
            splash_image_uri = starter_pack.splash_image.url
        else:
            splash_image_uri = static("og-starterpack.png")
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
                "url": request.build_absolute_uri(splash_image_uri),
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
        try:
            access_account = request.user.accountaccess.account
        except AccountAccess.DoesNotExist:
            access_account = None

        accounts = accounts.annotate(
            is_following=Exists(
                AccountFollowing.objects.filter(account=access_account, url=OuterRef("url")),
            )
        )

    paginator = Paginator(accounts, 50)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    owners = list(starter_pack.owners.select_related("accountaccess__account").order_by("username"))
    is_owner = request.user.is_authenticated and any(owner.id == request.user.id for owner in owners)
    header_avatars = pack_header_avatars([starter_pack.id], limit=18).get(starter_pack.id, [])

    return render(
        request,
        "starter_pack_accounts.html" if "HX-Request" in request.headers else "share_starter_pack.html",
        {
            "page_title": re.sub(r":\w+:", "", starter_pack.title).strip() + _(" - Mastodon Starter Pack"),
            "page": "starter_packs",
            "page_url": reverse("share_starter_pack", kwargs={"starter_pack_slug": starter_pack_slug}),
            "page_header": "FEDIDEVS",
            "page_subheader": "",
            "page_image": starter_pack.splash_image.url if starter_pack.splash_image else static("og-starterpack.png"),
            "page_description": starter_pack.description,
            "starter_pack": starter_pack,
            "is_owner": is_owner,
            "owners": owners,
            "header_avatars": header_avatars,
            "num_accounts": starter_pack.num_accounts,
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
    starter_pack = get_editable_pack(request, starter_pack_slug)
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


@login_required
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
    transaction.on_commit(lambda: follow_bg.delay(request.user.id, starter_pack_slug))
    FollowAllClick.objects.create(user=request.user, starter_pack=starter_pack)
    messages.success(request, _("Following all accounts in the starter pack. 🎉"))

    return redirect("share_starter_pack", starter_pack_slug=starter_pack.slug)


@shared_task
def update_starter_pack_splash_images(starter_pack_slug: str):
    starter_pack = StarterPack.objects.get(slug=starter_pack_slug)
    render_splash_image(starter_pack=starter_pack, host_attribution="fedidevs.com")


@shared_task
def follow_bg(user_id: int, starter_pack_slug: str):
    user = User.objects.get(pk=user_id)
    account_access = user.accountaccess
    instance = account_access.instance

    mastodon = None
    if not instance.is_misskey:
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

        try:
            if instance.is_misskey:
                resolve_and_follow_misskey(instance.url, account_access.access_token, account)
            else:
                resolve_and_follow_account(mastodon, account, instance)
        except FollowError:
            logger.info("%s failed to follow in bg %s", user.username, account.username_at_instance, exc_info=True)
            continue
