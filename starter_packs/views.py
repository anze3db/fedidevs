import logging
import re

import dramatiq
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.postgres.search import SearchQuery
from django.core.paginator import Paginator
from django.db import IntegrityError, models, transaction
from django.db.models import Exists, OuterRef, Q
from django.http import HttpResponse
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

from accounts.management.commands.crawlone import crawlone
from accounts.models import Account, Instance
from mastodon_auth.models import AccountFollowing
from starter_packs.models import StarterPack, StarterPackAccount
from stats.models import FollowAllClick

logger = logging.getLogger(__name__)
username_regex = re.compile(r"@?\b([A-Z0-9._%+-]+)@([A-Z0-9.-]+\.[A-Z]{2,})\b", re.IGNORECASE)


def starter_packs(request):
    tab = request.GET.get("tab")
    if tab not in ("community", "your", "containing"):
        tab = "community"

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
        .order_by("-created_at")
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
        .filter(in_starter_pack=True, instance_model__deleted_at__isnull=True)
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
        else:
            starter_pack.published_at = timezone.now()
        starter_pack.save(update_fields=["published_at", "updated_at"])

    response = HttpResponse()
    response["HX-Redirect"] = reverse("share_starter_pack", kwargs={"starter_pack_slug": starter_pack.slug})
    return response


@transaction.atomic
def toggle_account_to_starter_pack(request, starter_pack_slug, account_id):
    starter_pack = get_object_or_404(
        StarterPack, slug=starter_pack_slug, deleted_at__isnull=True, created_by=request.user
    )
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
        StarterPackAccount.objects.create(
            starter_pack=starter_pack,
            account_id=account_id,
        )

    return render(
        request,
        "starter_pack_stats.html",
        {
            "starter_pack": starter_pack,
            "review": request.POST.get("review"),
            "num_accounts": StarterPackAccount.objects.filter(starter_pack=starter_pack).count(),
        },
    )


def share_starter_pack(request, starter_pack_slug):
    starter_pack = get_object_or_404(StarterPack, slug=starter_pack_slug, deleted_at__isnull=True)
    accounts = (
        Account.objects.filter(
            starterpackaccount__starter_pack=starter_pack,
            instance_model__deleted_at__isnull=True,
            discoverable=True,
        )
        .select_related("accountlookup", "instance_model")
        .order_by("-followers_count")
    )

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
            "num_hidden_accounts": Account.objects.exclude(discoverable=True, instance_model__deleted_at__isnull=True)
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
