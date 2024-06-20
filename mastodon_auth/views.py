import logging
from datetime import datetime, timezone
from uuid import uuid4

import dramatiq
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from mastodon import Mastodon, MastodonNetworkError
from mastodon.errors import MastodonAPIError, MastodonNotFoundError, MastodonUnauthorizedError

from accounts.models import Account
from mastodon_auth.models import AccountAccess, AccountFollowing, Instance
from stats.models import FollowClick

login_scopes = app_scopes = (
    "read:accounts",
    "read:follows",
    "write:follows",
)
login_scopes = ("read:accounts", "read:follows", "write:follows")


@require_POST
def login(request):
    api_base_url = request.POST.get("instance", "").strip()
    api_base_url = api_base_url.replace("https://", "").replace("http://", "")

    if api_base_url.endswith("/"):
        api_base_url = api_base_url[0:-1]

    if "/" in api_base_url:
        api_base_url = api_base_url.split("/")[0]

    instance = Instance.objects.filter(url=api_base_url).first()

    if not instance:
        try:
            (client_id, client_secret) = Mastodon.create_app(
                client_name=settings.MSTDN_CLIENT_NAME,
                scopes=app_scopes,
                redirect_uris=settings.MSTDN_REDIRECT_URI,
                website="https://fedidevs.com",
                api_base_url=api_base_url,
            )
        except MastodonNetworkError:
            return {
                "error": f"Invalid instance url: {api_base_url}",
            }

        instance = Instance(
            url=api_base_url,
            client_id=client_id,
            client_secret=client_secret,
            app_scopes=app_scopes,
        )
        instance.save()

    state = str(uuid4())

    mastodon = Mastodon(api_base_url=api_base_url, user_agent="fedidevs")
    auth_request_url = mastodon.auth_request_url(
        client_id=instance.client_id,
        state=state,
        redirect_uris=settings.MSTDN_REDIRECT_URI,
        scopes=login_scopes,
    )

    cache.set(f"oauth:{state}", instance.id, timeout=500)

    return redirect(auth_request_url)


def logout(request):
    user = request.user
    if not user.is_authenticated:
        return redirect("index")

    # TODO: Addd delete option
    # mastodon = Mastodon(
    #     client_id=user.account.instance.client_id,
    #     client_secret=user.account.instance.client_secret,
    #     api_base_url=user.account.instance.url,
    #     access_token=user.account.access_token,
    # )
    # mastodon.revoke_access_token()
    # AccountAccess.objects.filter(user=request.user).delete()
    auth_logout(request)
    return redirect("index")


def auth(request):
    code = request.GET.get("code")
    state = request.GET.get("state")

    instance_id = cache.get(f"oauth:{state}")
    assert instance_id, "State could not be found in cache"

    instance = Instance.objects.get(id=instance_id)

    mastodon = Mastodon(
        api_base_url=instance.url,
        client_id=instance.client_id,
        client_secret=instance.client_secret,
        user_agent="fedidevs",
    )

    access_token = mastodon.log_in(
        code=code,
        redirect_uri=settings.MSTDN_REDIRECT_URI,
        scopes=login_scopes,
    )

    now = datetime.now(tz=timezone.utc)
    logged_in_account = mastodon.me()
    account, _ = Account.objects.update_or_create(
        account_id=logged_in_account["id"],
        instance=instance,
        defaults={
            "username": logged_in_account.get("username"),
            "acct": logged_in_account.get("acct"),
            "display_name": logged_in_account.get("display_name"),
            "locked": logged_in_account.get("locked"),
            "bot": logged_in_account.get("bot"),
            "group": logged_in_account.get("group"),
            "discoverable": logged_in_account.get("discoverable"),
            "noindex": logged_in_account.get("noindex"),
            "created_at": logged_in_account.get("created_at"),
            "last_status_at": logged_in_account.get("last_status_at"),
            "last_sync_at": now,
            "followers_count": logged_in_account.get("followers_count"),
            "following_count": logged_in_account.get("following_count"),
            "statuses_count": logged_in_account.get("statuses_count"),
            "note": logged_in_account.get("note"),
            "url": logged_in_account.get("url"),
            "avatar": logged_in_account.get("avatar"),
            "avatar_static": logged_in_account.get("avatar_static"),
            "header": logged_in_account.get("header"),
            "header_static": logged_in_account.get("header_static"),
            "emojis": logged_in_account.get("emojis"),
            "roles": logged_in_account.get("roles", []),
            "fields": logged_in_account.get("fields"),
        },
    )

    user, _ = User.objects.get_or_create(username=account.username_at_instance)

    AccountAccess.objects.update_or_create(
        user=user,
        defaults={
            "account": account,
            "instance": instance,
            "access_token": access_token,
        },
    )
    # force log the user in
    auth_login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])

    transaction.on_commit(lambda: sync_following.send(user.id))
    messages.success(request, "Login successful, your following list is syncing...")

    return redirect("index")


@dramatiq.actor
def sync_following(user_id: int):
    user = User.objects.get(pk=user_id)
    account_access = user.accountaccess
    instance = account_access.instance
    account = account_access.account
    mastodon = Mastodon(
        api_base_url=instance.url,
        client_id=instance.client_id,
        client_secret=instance.client_secret,
        access_token=account_access.access_token,
        user_agent="fedidevs",
    )
    accounts = mastodon.account_following(account.account_id)
    to_create = []
    while accounts:
        for following in accounts:
            to_create.append(
                AccountFollowing(
                    account=account,
                    url=following["url"],
                )
            )
        accounts = mastodon.fetch_next(accounts)
    AccountFollowing.objects.filter(account=account).exclude(url__in=[x.url for x in to_create]).delete()
    AccountFollowing.objects.bulk_create(to_create, batch_size=1000, ignore_conflicts=True)


def follow(request, account_id: int):
    def err_response(msg):
        return render(
            request,
            "v2/follow_response.html",
            {"err_msg": msg},
        )

    account_access = request.user.accountaccess
    instance = account_access.instance
    mastodon = Mastodon(
        api_base_url=instance.url,
        client_id=instance.client_id,
        client_secret=instance.client_secret,
        access_token=account_access.access_token,
        user_agent="fedidevs",
    )
    account = Account.objects.get(pk=account_id)
    if account.instance == instance.url:
        account_id = account.account_id
    else:
        try:
            local_account = mastodon.account_lookup(acct=account.username_at_instance)
        except MastodonNotFoundError:
            logging.warning("Account not found on instance %s", account.username_at_instance)
            return err_response("Account not found")
        except MastodonUnauthorizedError:
            logging.warning("Not authorized %s", account.username_at_instance)
            return err_response("Not Authorized")
        except MastodonAPIError:
            logging.error("Unknown error when following %s", account.username_at_instance)
            return err_response("Failed to follow")
        account_id = local_account["id"]

    try:
        mastodon.account_follow(account_id)
    except MastodonUnauthorizedError:
        return err_response("Unothorized")
    except MastodonAPIError:
        # We weren't able to follow the user. Maybe the account was moved?
        try:
            local_account = mastodon.account_lookup(acct=account.username_at_instance)
        except MastodonNotFoundError:
            logging.warning("Account not found on instance %s", account.username_at_instance)
            return err_response("Account not found")
        if moved := local_account.get("moved"):
            account.moved = moved
            account.save(update_fields=("moved",))
            logging.warning("Account %s moved", account.username_at_instance)
            return err_response("Account has moved")

        logging.error("Unknown error when following %s", account.username_at_instance)
        return err_response("Failed to follow")

    AccountFollowing.objects.get_or_create(account=request.user.accountaccess.account, url=account.url)
    FollowClick.objects.create(user=request.user, url=account.url)

    return render(
        request,
        "v2/follow_response.html",
    )
