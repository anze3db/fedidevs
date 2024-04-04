from datetime import datetime, timezone
from uuid import uuid4

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import User
from django.core.cache import cache
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from mastodon import Mastodon, MastodonNetworkError

from accounts.models import Account
from mastodon_auth.models import AccountAccess, AccountFollowing, Instance

app_scopes = (
    "read:accounts",
    "read:blocks",
    "read:favourites",
    "read:filters",
    "read:follows",
    "read:lists",
    "read:mutes",
    "read:notifications",
    "read:search",
    "read:statuses",
    "read:bookmarks",
    "write:accounts",
    "write:blocks",
    "write:favourites",
    "write:filters",
    "write:follows",
    "write:lists",
    "write:media",
    "write:mutes",
    "write:notifications",
    "write:reports",
    "write:statuses",
    "write:bookmarks",
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
    # TODO: Move to bg
    accounts = mastodon.account_following(logged_in_account["id"])
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
    AccountFollowing.objects.bulk_create(to_create, batch_size=1000, ignore_conflicts=True)
    AccountFollowing.objects.filter(account=account).exclude(url__in=[x.url for x in to_create]).delete()

    # force log the user in
    auth_login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])

    messages.success(request, "Login successful, your following list is syncing...")

    return redirect("index")
