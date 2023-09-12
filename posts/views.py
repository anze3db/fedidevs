import datetime as dt

from django.db.models import Q
from django.shortcuts import render

from accounts.models import LANGUAGES
from posts.models import Post


# Create your views here.
def index(request, lang: str | None = None):
    langs_map = {l.code: l for l in LANGUAGES}
    selected_lang = langs_map.get(lang)
    search_query = Q(created_at__gte=dt.date.today() - dt.timedelta(days=1))
    if selected_lang:
        search_query &= Q(account__accountlookup__language=selected_lang.code)
    posts = Post.objects.filter(search_query).order_by("-favourites_count")[:100]
    return render(
        request,
        "posts.html",
        {
            "page_title": "FediDevs | List of software developers on Mastodon"
            if not selected_lang
            else f"FediDevs | List of {selected_lang.name} developers on Mastodon",
            "page_description": "Discover amazing developers from across the fediverse."
            if not selected_lang
            else f"Discover amazing {selected_lang.name} developers from across the fediverse.",
            "page_image": "og.png",
            "posts": posts,
            "selected_lang": selected_lang,
            "languages": LANGUAGES,
            "adjectives": [
                "great",
                "awesome",
                "marvelous",
                "wonderful",
                "fantastic",
                "amazing",
                "incredible",
                "superb",
                "spectacular",
                "stupendous",
                "fabulous",
                "brilliant",
                "magnificent",
                "excellent",
                "outstanding",
                "terrific",
            ],
        },
    )
