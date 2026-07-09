import datetime as dt
import logging
from urllib.parse import urljoin
from uuid import uuid4

import httpx
from celery import shared_task
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
    MastodonIllegalArgumentError,
    MastodonInternalServerError,
    MastodonNetworkError,
)
from mastodon.errors import MastodonAPIError

from accounts.misskey import user_to_mastodon
from accounts.misskey_api import (
    build_miauth_url,
    detect_software,
    get_following_urls,
    is_misskey_family,
    miauth_check,
)
from accounts.models import Account
from mastodon_auth.forms import MastodonLoginForm
from mastodon_auth.models import AccountAccess, AccountFollowing, Instance
from mastodon_auth.oauth import AppRegistrationError, authorize_url, is_pleroma, register_app
from starter_packs.utils import FollowError, resolve_and_follow_account, resolve_and_follow_misskey
from stats.models import FollowClick

logger = logging.getLogger(__name__)
# Coarse OAuth scopes understood by BOTH Mastodon and the Misskey family
# (Misskey/Sharkey/Firefish only recognize coarse read/write/follow — not
# Mastodon's granular read:accounts/read:follows/read:search/read:lists, which
# made their grant page error out with "an error has occurred"). fedidevs only
# reads profiles/follows/search (read) and follows accounts (follow).
SCOPES = ("read", "follow")

# How long an in-flight OAuth/MiAuth handshake stays valid between the redirect
# to the instance and the callback. Generous enough to cover a slow mobile login
# with 2FA on the consent screen; expiry past this just asks the user to retry.
OAUTH_STATE_TTL = 60 * 30  # 30 minutes


@require_POST
def login(request):
    form = MastodonLoginForm(request.POST)
    if not form.is_valid():
        messages.error(request, form.errors["instance"][0])
        return redirect("/")

    api_base_url = form.cleaned_data["instance"]
    next_url = form.cleaned_data.get("next") or "/"

    try:
        res = httpx.get(f"https://{api_base_url}/.well-known/host-meta", timeout=10.0)
        if 300 <= res.status_code < 400:
            logger.info("Redirected to %s", res.headers["Location"])
            api_base_url = res.headers["Location"].split("/")[2]
    except httpx.RequestError as e:
        # Instance unreachable (DNS failure, refused, timeout). Not a bug on our
        # side, so warn (breadcrumb) rather than error (Sentry event).
        logger.warning("login host-meta unreachable for %s: %s", api_base_url, e)
        messages.error(request, f"Mastodon instance not found. Is the URL correct? `{api_base_url}`")
        return redirect("/")
    except httpx.InvalidURL as e:
        logger.warning("login host-meta invalid url for %s: %s", api_base_url, e)
        messages.error(request, _("The URL provided is invalid.") + f" `{api_base_url}`")
        return redirect("/")

    instance = Instance.objects.filter(url=api_base_url).first()

    # Misskey-family instances (Sharkey/Firefish/…) can't use Mastodon's OAuth
    # consent page (it errors out), so route them through native MiAuth instead.
    # Detection is cached on the instance row to avoid a nodeinfo hit each login.
    software = (instance.software if instance else "") or detect_software(api_base_url) or ""
    if is_misskey_family(software):
        if instance is None:
            instance = Instance(url=api_base_url, client_id="", client_secret="", software=software)
            instance.save()
        elif instance.software != software:
            instance.software = software
            instance.save(update_fields=["software", "updated_at"])

        session = str(uuid4())
        callback = urljoin(settings.MSTDN_REDIRECT_URI, "/miauth_callback/")
        cache.set(f"miauth:{session}", instance.id, timeout=OAUTH_STATE_TTL)
        cache.set(f"miauth:{session}:next", next_url, timeout=OAUTH_STATE_TTL)
        return redirect(build_miauth_url(api_base_url, session, callback, settings.MSTDN_CLIENT_NAME))

    desired_scopes = " ".join(SCOPES)

    # Register the OAuth app, or RE-register it when the stored app predates a
    # scope change (granted scopes are fixed at app-creation time on the
    # instance, so a stale app would still request the old scopes). Existing
    # access tokens keep working — they authenticate via their bearer token, not
    # the app's client_id/secret — so rotating the credentials here is safe.
    if not instance or instance.scopes != desired_scopes:
        try:
            client_id, client_secret = register_app(
                api_base_url=api_base_url,
                client_name=settings.MSTDN_CLIENT_NAME,
                scopes=SCOPES,
                redirect_uris=settings.MSTDN_REDIRECT_URI,
                website="https://fedidevs.com",
            )
        except AppRegistrationError as e:
            # App registration failed. The common cause is the instance
            # rate-limiting POST /api/v1/apps (e.status_code == 429); it can also
            # be a transient network error (e.status_code is None). If we already
            # have working credentials for this instance, reuse them so login still
            # works (with the previously granted scopes); otherwise tell the user
            # it's temporarily unavailable. Not an app bug, so warn (breadcrumb)
            # rather than error.
            if instance and instance.client_id and instance.client_secret:
                logger.warning(
                    "login register_app failed for %s (status=%s); reusing existing app credentials: %s",
                    api_base_url,
                    e.status_code,
                    e,
                )
            else:
                logger.warning(
                    "login register_app could not register app on %s (status=%s): %s",
                    api_base_url,
                    e.status_code,
                    e,
                )
                messages.error(
                    request,
                    _(
                        "This instance is temporarily unavailable for login (it may be rate limiting requests). "
                        "Please try again in a few minutes."
                    )
                    + f" `{api_base_url}`",
                )
                return redirect("/")
        else:
            if instance is None:
                instance = Instance(url=api_base_url)
            instance.client_id = client_id
            instance.client_secret = client_secret
            instance.scopes = desired_scopes
            instance.software = software
            instance.save()
    elif instance.software != software:
        instance.software = software
        instance.save(update_fields=["software", "updated_at"])

    state = str(uuid4())

    # Pleroma's "already authorized" shortcut redirects back without a code, so
    # force its consent flow (which does issue a code). Harmless to omit for
    # Mastodon, where force_login would add an unwanted re-login step.
    auth_request_url = authorize_url(
        api_base_url=api_base_url,
        client_id=instance.client_id,
        redirect_uri=settings.MSTDN_REDIRECT_URI,
        scopes=SCOPES,
        state=state,
        force_login=is_pleroma(software),
    )

    cache.set(f"oauth:{state}", instance.id, timeout=OAUTH_STATE_TTL)
    cache.set(f"oauth:{state}:next", next_url, timeout=OAUTH_STATE_TTL)

    # Log exactly what we hand the instance, so an empty callback (no code/state)
    # can be traced back to the redirect_uri / response_type we requested.
    logger.info(
        "login redirecting to OAuth authorize for %s: redirect_uri=%s state=%s url=%s",
        api_base_url,
        settings.MSTDN_REDIRECT_URI,
        state,
        auth_request_url,
    )

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

    # The instance rejected the authorization or the user denied it. OAuth error
    # redirects echo back ?error=...&error_description=... (and usually state).
    error = request.GET.get("error")
    if error:
        if error == "access_denied":
            # The user clicked "Cancel"/"Deny" on their instance's consent screen
            # (or the instance rejected the app). Expected, user-recoverable — log
            # at warning so it doesn't page us.
            logger.warning(
                "auth callback OAuth denied: error=%s description=%s",
                error,
                request.GET.get("error_description"),
            )
        else:
            # Other OAuth errors (invalid_scope, unauthorized_client, server_error,
            # ...) can point at a real app misconfiguration — keep them at error.
            logger.error(
                "auth callback OAuth error from instance: error=%s description=%s",
                error,
                request.GET.get("error_description"),
            )
        messages.error(request, _("Login was cancelled or rejected by the instance. Please try again."))
        return redirect("index")

    if not code or not state:
        # The instance redirected back without the authorization code. This is a
        # real, user-facing login failure (they saw "Invalid request") — log it at
        # ERROR with full context so we can tell a genuine failure from a bare
        # crawler/bookmark hit and see what the instance actually sent.
        logger.error("auth callback missing code/state")
        messages.error(request, _("Invalid request, please try again"))
        return redirect("index")

    instance_id = cache.get(f"oauth:{state}")
    next_url = cache.get(f"oauth:{state}:next")
    if not instance_id:
        # We have a state but no cached entry for it: the handshake expired (the
        # user lingered past OAUTH_STATE_TTL on the consent screen), was evicted,
        # or a cross-process cache miss. User-recoverable, not a bug — log at
        # warning so it doesn't page us.
        logger.warning("auth callback unknown/expired OAuth state %s", state)
        messages.error(request, _("Your login session expired, please try again."))
        return redirect("index")

    instance = Instance.objects.get(id=instance_id)

    mastodon = Mastodon(
        api_base_url=instance.url,
        client_id=instance.client_id,
        client_secret=instance.client_secret,
        user_agent="fedidevs",
        version_check_mode="none",
    )

    try:
        access_token = mastodon.log_in(
            code=code,
            redirect_uri=settings.MSTDN_REDIRECT_URI,
            scopes=SCOPES,
        )
    except MastodonNetworkError as e:
        # Instance unreachable mid-flow — connectivity, not a bug.
        logger.warning("login log_in unreachable for %s: %s", instance.url, e)
        messages.error(request, _("Network error, please try again."))
        return redirect("index")
    except MastodonIllegalArgumentError as e:
        if "invalid_grant" in str(e):
            # The authorization code was expired, already used, or otherwise no
            # longer valid (e.g. the user reloaded the callback or took too long).
            # User-recoverable, not a bug — log at warning so it doesn't page us.
            logger.warning("login log_in invalid_grant for %s: %s", instance.url, e)
            messages.error(request, _("Your login session expired, please try again."))
            return redirect("index")
        logger.exception("login log_in invalid argument error for %s", instance.url)
        messages.error(request, _("Authorization flow is not supported by this instance."))
        return redirect("index")
    except MastodonInternalServerError:
        logger.exception("login log_in instance server error for %s", instance.url)
        messages.error(request, _("The instance server encountered an error, please try again later."))
        return redirect("index")
    except MastodonAPIError:
        # Pleroma (and some other Mastodon-compatible servers) report the granted
        # OAuth scopes in granular form (e.g. "read:accounts ... follow") instead
        # of echoing back the coarse "read" we requested. mastodon.py's strict
        # subset check then raises even though the token exchange itself
        # succeeded — the access token is already set on the client at that point,
        # so fall back to it rather than failing the login.
        access_token = mastodon.access_token
        if not access_token:
            logger.exception("login log_in api error for %s", instance.url)
            messages.error(request, _("Unable to complete login, please try again."))
            return redirect("index")
        # Not a failure: token obtained, only the scope-subset check tripped.
        logger.info("login scope check bypassed for %s", instance.url)

    now = timezone.now()
    try:
        logged_in_account = mastodon.me()
    except MastodonAPIError:
        logger.exception("login me() api error for %s", instance.url)
        messages.error(request, _("Unable to fetch account information, please try again."))
        return redirect("index")
    # Pleroma (and some other Mastodon-compatible servers) return null/omit
    # fields that vanilla Mastodon always sends, including the NOT NULL booleans
    # (discoverable, group) and counts. Coerce nulls to safe defaults so the
    # account row can be saved.
    account, __ = Account.objects.update_or_create(
        account_id=logged_in_account["id"],
        instance=instance,
        defaults={
            "username": logged_in_account.get("username"),
            "acct": logged_in_account.get("acct"),
            "display_name": logged_in_account.get("display_name") or "",
            "locked": logged_in_account.get("locked") or False,
            "bot": logged_in_account.get("bot") or False,
            "group": logged_in_account.get("group") or False,
            "discoverable": logged_in_account.get("discoverable") or False,
            "noindex": logged_in_account.get("noindex"),
            "created_at": logged_in_account.get("created_at") or now,
            # Mastodon sends last_status_at as a bare "YYYY-MM-DD" date; parse it
            # to an aware datetime so it doesn't coerce to a naive one and warn.
            "last_status_at": _parse_dt(logged_in_account.get("last_status_at")),
            "last_sync_at": now,
            "followers_count": logged_in_account.get("followers_count") or 0,
            "following_count": logged_in_account.get("following_count") or 0,
            "statuses_count": logged_in_account.get("statuses_count") or 0,
            "note": logged_in_account.get("note") or "",
            "url": logged_in_account.get("url") or "",
            "activitypub_id": logged_in_account.get("uri"),
            "avatar": logged_in_account.get("avatar") or "",
            "avatar_static": logged_in_account.get("avatar_static") or "",
            "header": logged_in_account.get("header") or "",
            "header_static": logged_in_account.get("header_static") or "",
            "emojis": logged_in_account.get("emojis") or [],
            "roles": logged_in_account.get("roles") or [],
            "fields": logged_in_account.get("fields") or [],
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

    transaction.on_commit(lambda: sync_following.delay(user.id))

    if next_url:
        return redirect(next_url)

    return redirect("index")


def _parse_dt(value):
    """Coerce an ISO timestamp string or a date/datetime into an aware datetime.

    The mastodon.py client already parses date fields into (often naive) datetime
    objects, while the raw httpx/miauth paths pass ISO strings. Handle both, plus
    bare dates, and always return an aware datetime (or None)."""
    if not value:
        return None
    if isinstance(value, str):
        value = dt.datetime.fromisoformat(value)
    elif not isinstance(value, dt.datetime) and isinstance(value, dt.date):
        value = dt.datetime.combine(value, dt.time.min)
    if value.tzinfo is None:
        value = timezone.make_aware(value)
    return value


def miauth_callback(request):
    """Complete a native MiAuth login for a Misskey-family instance.

    Misskey redirects here with `?session=<uuid>` after the user approves on its
    native consent screen. We exchange the session for an access token + user,
    then mirror the same Account/AccountAccess bookkeeping as the Mastodon auth().
    """
    session = request.GET.get("session")
    if not session:
        logger.error("miauth callback missing session")
        messages.error(request, _("Invalid request, please try again"))
        return redirect("index")

    instance_id = cache.get(f"miauth:{session}")
    next_url = cache.get(f"miauth:{session}:next")
    if not instance_id:
        # We have a session but no cached entry: the handshake expired (past
        # OAUTH_STATE_TTL), was evicted, or a cross-process cache miss.
        # User-recoverable, not a bug — log at warning so it doesn't page us.
        logger.warning("miauth callback unknown/expired session %s", session)
        messages.error(request, _("Your login session expired, please try again."))
        return redirect("index")

    instance = Instance.objects.get(id=instance_id)
    data = miauth_check(instance.url, session)
    if not data:
        logger.error("miauth check failed for %s", instance.url)
        messages.error(request, _("Unable to complete login, please try again."))
        return redirect("index")

    # Reuse the crawler's Misskey→Account mapping so the row (incl. the correct
    # /users/{id} activitypub_id) matches what the crawler would produce.
    mapped = user_to_mastodon(data["user"], instance.url)
    if not mapped:
        logger.error("miauth user mapping failed for %s", instance.url)
        messages.error(request, _("Unable to fetch account information, please try again."))
        return redirect("index")

    now = timezone.now()
    account, __ = Account.objects.update_or_create(
        account_id=mapped["id"],
        instance=instance.url,
        defaults={
            "username": mapped["username"],
            "acct": mapped["acct"],
            "display_name": mapped["display_name"],
            "locked": mapped["locked"],
            "bot": mapped["bot"],
            "group": mapped["group"],
            "discoverable": mapped["discoverable"],
            "noindex": mapped["noindex"],
            "created_at": _parse_dt(mapped["created_at"]),
            "last_status_at": _parse_dt(mapped["last_status_at"]),
            "last_sync_at": now,
            "followers_count": mapped["followers_count"],
            "following_count": mapped["following_count"],
            "statuses_count": mapped["statuses_count"],
            "note": mapped["note"],
            "url": mapped["url"],
            "activitypub_id": mapped["uri"],
            "avatar": mapped["avatar"],
            "avatar_static": mapped["avatar_static"],
            "header": mapped["header"],
            "header_static": mapped["header_static"],
            "emojis": mapped["emojis"],
            "roles": mapped["roles"],
            "fields": mapped["fields"],
            "username_at_instance": f"@{mapped['username'].lower()}@{instance.url.lower()}",
        },
    )

    user, __ = User.objects.get_or_create(username=account.username_at_instance)
    AccountAccess.objects.update_or_create(
        user=user,
        defaults={
            "account": account,
            "instance": instance,
            "access_token": data["token"],
        },
    )
    auth_login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])
    transaction.on_commit(lambda: sync_following.delay(user.id))

    return redirect(next_url or "index")


def get_mastodon_following_urls(instance_url: str, token: str, account_id: str) -> list[str] | None:
    """Return the profile URLs of everyone the account follows (paginated).

    Hits /api/v1/accounts/{id}/following directly with httpx instead of going
    through mastodon.py. The library casts every entry into a fully typed
    Account entity on each response (recursive reflection + dateutil date
    parsing), which costs ~2s per 40-account page on low-power hosts even though
    we only read each followee's `url`. A plain JSON fetch with Link-header
    pagination is dramatically cheaper.

    Returns the list of URLs, or None if the very first request fails (so the
    caller can skip the sync instead of wiping the existing following on a
    transient error).
    """
    urls: list[str] = []
    url = f"https://{instance_url}/api/v1/accounts/{account_id}/following"
    params: dict | None = {"limit": 80}
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "fedidevs"}
    with httpx.Client(headers=headers, timeout=10.0) as client:
        # Bound the loop so a server with broken pagination can't spin forever.
        for page_num in range(200):
            try:
                res = client.get(url, params=params)
                res.raise_for_status()
            except httpx.HTTPError:
                logger.info("Error fetching Mastodon following for %s", instance_url)
                # First page failed: signal failure so we don't wipe existing rows.
                return None if page_num == 0 else urls
            page = res.json()
            if not page:
                break
            for following in page:
                if following.get("url"):
                    urls.append(following["url"])
            # Mastodon advertises the next page via a Link header (rel="next");
            # its absence means we've reached the end.
            next_link = res.links.get("next")
            if not next_link:
                break
            url = next_link["url"]  # already carries max_id + limit
            params = None
        else:
            logger.warning("Mastodon following pagination hit page cap for %s", instance_url)
    return urls


@shared_task
def sync_following(user_id: int):
    user = User.objects.get(pk=user_id)
    account_access = user.accountaccess
    instance = account_access.instance
    account = account_access.account

    if instance.is_misskey:
        urls = get_following_urls(instance.url, account_access.access_token, account.account_id)
        AccountFollowing.objects.filter(account=account).exclude(url__in=urls).delete()
        AccountFollowing.objects.bulk_create(
            [AccountFollowing(account=account, url=url) for url in urls],
            batch_size=1000,
            ignore_conflicts=True,
        )
        return

    urls = get_mastodon_following_urls(instance.url, account_access.access_token, account.account_id)
    if urls is None:
        # Couldn't reach the instance at all; leave the existing following intact.
        return
    AccountFollowing.objects.filter(account=account).exclude(url__in=urls).delete()
    AccountFollowing.objects.bulk_create(
        [AccountFollowing(account=account, url=url) for url in urls],
        batch_size=1000,
        ignore_conflicts=True,
    )


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
    account = Account.objects.get(pk=account_id)

    try:
        if instance.is_misskey:
            resolve_and_follow_misskey(instance.url, account_access.access_token, account)
        else:
            mastodon = Mastodon(
                api_base_url=instance.url,
                client_id=instance.client_id,
                client_secret=instance.client_secret,
                access_token=account_access.access_token,
                user_agent="fedidevs",
                request_timeout=5,
                version_check_mode="none",
            )
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
        version_check_mode="none",
    )
    try:
        res = mastodon.search_v2(q=query)
        status = res.statuses[0]
    except:  # noqa: E722
        logging.warning("Failed to redirect", exc_info=True)
        # TODO: Handle scope error by asking for an additional scope
        return redirect(query)
    return redirect(f"https://{instance.url}/@{status['account']['acct']}/{status['id']}")
