import datetime as dt

from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import LANGUAGES
from posts.models import Post


# Create your views here.
def index(
    request,
    lang: str | None = None,
    date: dt.date | None = None,
):
    langs_map = {l.code: l for l in LANGUAGES}
    selected_lang = langs_map.get(lang)
    if not date:
        date = timezone.now().date() - dt.timedelta(days=1)
        if lang:
            return redirect(f"{selected_lang.code}-posts", date=date)
        else:
            return redirect("posts", date=date)

    search_query = Q(
        created_at__gte=date,
        created_at__lt=date + dt.timedelta(days=1),
        visibility="public",
        favourites_count__gt=0,
    )
    if selected_lang:
        search_query &= Q(account__accountlookup__language=selected_lang.code)
    posts = (
        Post.objects.filter(search_query)
        .order_by("-favourites_count")
        .prefetch_related("account", "account__accountlookup_set")[:20]
    )
    # List of date objects. The first one is the date 2023-09-12 and then one item for every day until the current date
    dates = [
        dt.date.today() - dt.timedelta(days=i)
        for i in range(1, (dt.date.today() - dt.date(2023, 9, 11)).days)
    ]
    dates = [{"value": date.strftime("%Y-%m-%d"), "display": date} for date in dates]
    return render(
        request,
        "posts.html",
        {
            "page_title": "FediDevs POSTS | Daily Most Favourited Mastodon Posts"
            if not selected_lang
            else f"FediDevs POSTS | Daily Most Favourited Mastodon Posts in {selected_lang.name}",
            "page_header": "FEDIDEVS POSTS",
            "page_description": "Discover amazing posts from across the fediverse. Updated daily."
            if not selected_lang
            else f"Discover amazing {selected_lang.name} posts from across the fediverse. Updated daily.",
            "page_image": "og-posts.png",
            "posts": posts,
            "selected_lang": selected_lang,
            "languages": LANGUAGES,
            "posts_date": date,
            "dates": dates,
        },
    )
