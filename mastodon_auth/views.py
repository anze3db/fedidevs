import logging
from uuid import uuid4

import dramatiq
import httpx
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from mastodon import (
    Mastodon,
    MastodonError,
    MastodonIllegalArgumentError,
    MastodonNetworkError,
)
from mastodon.errors import MastodonAPIError

from accounts.models import Account
from mastodon_auth.models import AccountAccess, AccountFollowing, Instance
from starter_packs.utils import FollowError, resolve_and_follow_account
from stats.models import FollowClick

logger = logging.getLogger(__name__)
app_scopes = (
    "read:accounts",
    "read:follows",
    "read:search",
    "write:follows",
    "read:lists",
    "write:lists",
)
login_scopes = ("read:accounts", "read:follows", "write:follows", "read:search")


@require_POST
def login(request):
    api_base_url = request.POST.get("instance", "").strip().lower()
    api_base_url = api_base_url.replace("https://", "").replace("http://", "")
    next_url = request.POST.get("next", "/")

    if api_base_url.endswith("/"):
        api_base_url = api_base_url[0:-1]

    if "/" in api_base_url:
        api_base_url = api_base_url.split("/")[0]

    if "@" in api_base_url:
        api_base_url = api_base_url.split("@")[-1]

    # Encode internationalized domain names (IDN) to ASCII using IDNA encoding
    try:
        api_base_url = api_base_url.encode("idna").decode("ascii")
    except (UnicodeError, UnicodeDecodeError, UnicodeEncodeError):
        messages.error(request, _("Invalid instance URL. Please enter a valid Mastodon instance domain name."))
        return redirect("/")

    try:
        res = httpx.get(f"https://{api_base_url}/.well-known/host-meta", timeout=10.0)
        if 300 <= res.status_code < 400:
            logger.info("Redirected to %s", res.headers["Location"])
            api_base_url = res.headers["Location"].split("/")[2]
    except httpx.RequestError:
        messages.error(request, f"Mastodon instance not found. Is the URL correct? `{api_base_url}`")
        return redirect("/")
    except httpx.InvalidURL:
        messages.error(request, _("The URL provided is invalid.") + f" `{api_base_url}`")
        return redirect("/")

    instance = Instance.objects.filter(url=api_base_url).first()

    if not instance:
        try:
            (client_id, client_secret) = Mastodon.create_app(
                client_name=settings.MSTDN_CLIENT_NAME,
                scopes=app_scopes,
                redirect_uris=settings.MSTDN_REDIRECT_URI,
                website="https://fedidevs.com",
                api_base_url=api_base_url,
                user_agent="fedidevs",
            )
        except MastodonNetworkError:
            messages.info(request, _("Network error, is the instance url correct?") + f" `{api_base_url}`")
            return redirect("/")
        except KeyError:
            messages.error(
                request,
                _("Unable to create app on your instance. Is it a Mastodon compatible instance?")
                + f" `{api_base_url}`",
            )
            return redirect("/")
        except TypeError:
            messages.error(
                request,
                _("Unable to create app on your instance. Is it a Mastodon compatible instance?")
                + f" `{api_base_url}`",
            )
            return redirect("/")

        instance = Instance(
            url=api_base_url,
            client_id=client_id,
            client_secret=client_secret,
        )
        instance.save()

    state = str(uuid4())

    mastodon = Mastodon(api_base_url=api_base_url, user_agent="fedidevs", version_check_mode="none")
    try:
        auth_request_url = mastodon.auth_request_url(
            client_id=instance.client_id,
            state=state,
            redirect_uris=settings.MSTDN_REDIRECT_URI,
            scopes=login_scopes,
        )
    except MastodonError as e:
        messages.error(request, _("Unable to connect to the instance. Is it a Mastodon compatible instance?"))
        logger.info("login api error %s", e)
        return redirect("index")

    cache.set(f"oauth:{state}", instance.id, timeout=500)
    cache.set(f"oauth:{state}:next", next_url, timeout=500)

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
    #     user_agent="fedidevs",
    # )
    # mastodon.revoke_access_token()
    # AccountAccess.objects.filter(user=request.user).delete()
    auth_logout(request)
    return redirect("index")


def auth(request):
    code = request.GET.get("code")

    state = request.GET.get("state")

    if not code or not state:
        messages.error(request, _("Invalid request, please try again"))
        return redirect("index")

    instance_id = cache.get(f"oauth:{state}")
    next_url = cache.get(f"oauth:{state}:next")
    if not instance_id:
        messages.error(request, _("Invalid request, please try again"))
        return redirect("index")

    instance = Instance.objects.get(id=instance_id)

    mastodon = Mastodon(
        api_base_url=instance.url,
        client_id=instance.client_id,
        client_secret=instance.client_secret,
        user_agent="fedidevs",
    )

    if not code:
        auth_request_url = mastodon.auth_request_url(
            client_id=instance.client_id,
            state=state,
            redirect_uris=settings.MSTDN_REDIRECT_URI,
            scopes=login_scopes,
            force_login=True,
        )
        return redirect(auth_request_url)

    try:
        access_token = mastodon.log_in(
            code=code,
            redirect_uri=settings.MSTDN_REDIRECT_URI,
            scopes=login_scopes,
        )
    except MastodonNetworkError:
        messages.error(request, _("Network error, please try again."))
        return redirect("index")
    except MastodonIllegalArgumentError as e:
        messages.error(request, _("Authorization flow is not supported by this instance."))
        logger.info("login invalid argument error %s", e)
        return redirect("index")

    now = timezone.now()
    try:
        logged_in_account = mastodon.me()
    except MastodonAPIError as e:
        messages.error(request, _("Unable to fetch account information, please try again."))
        logger.info("login api error %s", e)
        return redirect("index")
    account, __ = Account.objects.update_or_create(
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
            "activitypub_id": logged_in_account.get("uri"),
            "avatar": logged_in_account.get("avatar"),
            "avatar_static": logged_in_account.get("avatar_static"),
            "header": logged_in_account.get("header"),
            "header_static": logged_in_account.get("header_static"),
            "emojis": logged_in_account.get("emojis"),
            "roles": logged_in_account.get("roles", []),
            "fields": logged_in_account.get("fields"),
            "username_at_instance": f"@{logged_in_account['username'].lower()}@{instance.url.lower()}",
        },
    )

    user, __ = User.objects.get_or_create(username=account.username_at_instance)

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

    if next_url:
        return redirect(next_url)

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
    try:
        accounts = mastodon.account_following(account.account_id)
    except MastodonError:
        logger.info("Error fetching following for user %s", user.username)
        return
    to_create = []
    while accounts:
        for following in accounts:
            to_create.append(
                AccountFollowing(
                    account=account,
                    url=following["url"],
                )
            )
        try:
            accounts = mastodon.fetch_next(accounts)
        except MastodonError:
            logger.info("Error fetching following for user %s", user.username)
            break
    AccountFollowing.objects.filter(account=account).exclude(url__in=[x.url for x in to_create]).delete()
    AccountFollowing.objects.bulk_create(to_create, batch_size=1000, ignore_conflicts=True)


@login_required
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
        request_timeout=5,
    )
    account = Account.objects.get(pk=account_id)

    try:
        resolve_and_follow_account(mastodon, account, instance)
    except FollowError as e:
        logger.info("%s failed to follow %s", request.user.username, account.username_at_instance, exc_info=True)
        return err_response(_(str(e)))

    AccountFollowing.objects.get_or_create(account=request.user.accountaccess.account, url=account.url)
    FollowClick.objects.create(user=request.user, url=account.url)

    return render(
        request,
        "v2/follow_response.html",
    )


def redirect_to_local(request, query: str):
    if not request.user.is_authenticated:
        return redirect(query)

    account_access = request.user.accountaccess
    instance = account_access.instance
    mastodon = Mastodon(
        api_base_url=instance.url,
        client_id=instance.client_id,
        client_secret=instance.client_secret,
        access_token=account_access.access_token,
        user_agent="fedidevs",
    )
    try:
        res = mastodon.search_v2(q=query)
        status = res.statuses[0]
    except:  # noqa: E722
        logging.warning("Failed to redirect", exc_info=True)
        # TODO: Handle scope error by asking for an additional scope
        return redirect(query)
    return redirect(f"https://{instance.url}/@{status['account']['acct']}/{status['id']}")
