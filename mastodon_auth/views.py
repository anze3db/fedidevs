from uuid import uuid4

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import User
from django.contrib.sites.shortcuts import get_current_site
from django.core.cache import cache
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from mastodon import Mastodon, MastodonNetworkError

from mastodon_auth.models import Account, Instance


def get_redirect_uri(request):
    site_domain = get_current_site(request).domain
    site_url = f"https://{site_domain}" if "8000" not in site_domain else f"http://{site_domain}"
    auth_path = reverse("mastodon_auth")
    return site_url + auth_path


@require_POST
def login(request):
    redirect_uri = get_redirect_uri(request)

    api_base_url = request.POST.get("instance", "").strip()
    api_base_url = api_base_url.replace("https://", "").replace("http://", "")

    scopes = (
        # "read:blocks",
        # "write:blocks",
        "read",
        "write:follows",
        # "read:mutes",
        # "write:mutes",
    )

    if api_base_url.endswith("/"):
        api_base_url = api_base_url[0:-1]

    if "/" in api_base_url:
        api_base_url = api_base_url.split("/")[0]

    instance = Instance.objects.filter(url=api_base_url).first()

    if not instance:
        try:
            (client_id, client_secret) = Mastodon.create_app(
                "fedidevs.com" if "8000" not in api_base_url else "local.fedidevs.com",
                scopes=scopes,
                redirect_uris=redirect_uri,
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
        redirect_uris=redirect_uri,
        scopes=scopes,
    )

    cache.set(f"oauth:{state}", instance.id, timeout=500)

    return redirect(auth_request_url)


def logout(request):
    auth_logout(request)
    return redirect("index")


def auth(request):
    redirect_uri = get_redirect_uri(request)

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

    scopes = ("read", "write:follows")

    access_token = mastodon.log_in(
        code=code,
        redirect_uri=redirect_uri,
        scopes=scopes,
    )

    # get username for Django user
    logged_in_account = mastodon.me()
    username = logged_in_account["username"]
    server_host = instance.url.replace("https://", "").replace("http://", "")
    username = f"@{username}@{server_host}"

    user = User.objects.filter(username=username).first()

    if not user:
        user = User(username=username)
        user.save()

    account = Account.objects.filter(user=user).first()

    if not account:
        account = Account(user=user, access_token=access_token, instance=instance)
        account.save()

    # force log the user in
    auth_login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])

    messages.success(request, "Login successful")

    return redirect("index")
