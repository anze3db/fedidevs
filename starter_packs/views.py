import logging
import re

import dramatiq
from django import forms
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode
from mastodon import Mastodon, MastodonAPIError, MastodonNotFoundError, MastodonUnauthorizedError

from accounts.models import Account
from mastodon_auth.models import AccountFollowing
from starter_packs.models import StarterPack, StarterPackAccount
from stats.models import FollowAllClick

logger = logging.getLogger(__name__)


def starter_packs(request):
    if request.user.is_anonymous:
        your_starter_packs = StarterPack.objects.none()
    else:
        your_starter_packs = (
            StarterPack.objects.filter(created_by=request.user, deleted_at__isnull=True)
            .order_by("-created_at")
            .prefetch_related("created_by")
        )

    return render(
        request,
        "starter_packs.html",
        {
            "page": "starter_packs",
            "page_title": "Mastodon Starter Pack Directory | Fedidevs",
            "page_header": "FEDIDEVS",
            "page_subheader": "",
            "starter_packs": StarterPack.objects.filter(deleted_at__isnull=True)
            .order_by("-created_at")
            .prefetch_related("created_by"),
            "your_starter_packs": your_starter_packs,
        },
    )


class StarterPackForm(forms.ModelForm):
    class Meta:
        model = StarterPack
        fields = ["title", "description"]


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
    if q := request.GET.get("q"):
        search = q.strip()

        # Check if searching with @username@instance and convert to instance/@username which is indexed
        regex = re.compile(r"(@?[a-zA-Z0-9_\.\-]+)@([a-zA-Z0-9_\.\-]+)")
        if regex.match(search):
            is_username = True
            if search.startswith("@"):
                search = search[1:]
            if len(splt := search.split("@")) == 2:
                username, instance = splt
                search = f"{instance}/@{username}"

        accounts = accounts.filter(
            accountlookup__text__icontains=search,
        )
    else:
        is_username = False

    paginator = Paginator(accounts, 50)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "add_accounts_list.html" if "HX-Request" in request.headers else "add_accounts.html",
        {
            "page": "starter_packs",
            "page_title": "Add accounts to your starter pack",
            "page_header": "FEDIDEVS",
            "page_subheader": "",
            "q": q,
            "is_username": is_username,
            "num_accounts": StarterPackAccount.objects.filter(starter_pack=starter_pack).count(),
            "accounts": page_obj,
            "starter_pack": starter_pack,
        },
    )


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
            "page_title": "Edit your starter pack",
            "page_header": "FEDIDEVS",
            "page_subheader": "",
            "form": form,
            "starter_pack": starter_pack,
        },
    )


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
                    forms.ValidationError("You already have a starter pack with this title."),
                )
    else:
        form = StarterPackForm()

    return render(
        request,
        "create_starter_pack.html",
        {
            "page": "starter_packs",
            "page_title": "Create a new starter pack",
            "page_header": "FEDIDEVS",
            "page_subheader": "",
            "page_description": "",
            "form": form,
        },
    )


def toggle_account_to_starter_pack(request, starter_pack_slug, account_id):
    starter_pack = get_object_or_404(
        StarterPack, slug=starter_pack_slug, deleted_at__isnull=True, created_by=request.user
    )
    if StarterPackAccount.objects.filter(starter_pack=starter_pack).count() > 150:
        return render(
            request,
            "starter_pack_stats.html",
            {
                "starter_pack": starter_pack,
                "num_accounts": StarterPackAccount.objects.filter(starter_pack=starter_pack).count(),
                "error": "You have reached the maximum number of accounts in a starter pack.",
            },
        )
    try:
        StarterPackAccount.objects.create(
            starter_pack=starter_pack,
            account_id=account_id,
        )
    except IntegrityError:
        StarterPackAccount.objects.filter(
            starter_pack=starter_pack,
            account_id=account_id,
        ).delete()
    return render(
        request,
        "starter_pack_stats.html",
        {
            "starter_pack": starter_pack,
            "num_accounts": StarterPackAccount.objects.filter(starter_pack=starter_pack).count(),
        },
    )


def share_starter_pack(request, starter_pack_slug):
    starter_pack = get_object_or_404(StarterPack, slug=starter_pack_slug, deleted_at__isnull=True)
    accounts = (
        Account.objects.filter(
            starterpackaccount__starter_pack=starter_pack,
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
        "share_starter_pack.html",
        {
            "page_title": starter_pack.title + " - Mastodon Starter Pack",
            "page": "starter_packs",
            "page_header": "FEDIDEVS",
            "page_subheader": "",
            "page_image": "og-starterpack.png",
            "page_description": starter_pack.description,
            "starter_pack": starter_pack,
            "num_accounts": accounts.count(),
            "accounts": page_obj,
        },
    )


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
    ).select_related("accountlookup", "instance_model")
    account_following = []
    for account in accounts:
        account_following.append(AccountFollowing(account=request.user.accountaccess.account, url=account.url))

    AccountFollowing.objects.bulk_create(account_following, ignore_conflicts=True)
    transaction.on_commit(lambda: follow_bg.send(request.user.id, starter_pack_slug))
    FollowAllClick.objects.create(user=request.user, starter_pack=starter_pack)

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
            except MastodonNotFoundError:
                logger.exception("Account not found on instance %s", account.username_at_instance)
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
