import datetime as dt

from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import LANGUAGES
from posts.models import DjangoConUS23Post, Post


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


def djangoconus(request, date: dt.date | None = None):
    search_query = Q(
        visibility="public",
    )
    order = request.GET.get("order")
    if order not in ("-favourites_count", "-created_at"):
        order = "-favourites_count"
    if date:
        date = date.date()
        search_query &= Q(
            created_at__gte=date, created_at__lt=date + dt.timedelta(days=1)
        )
    else:
        search_query &= Q(
            created_at__lte=dt.date(2023, 10, 20),
            created_at__gte=dt.date(2023, 10, 16),
        )

    posts = DjangoConUS23Post.objects.filter(search_query).order_by(order)
    # List of date objects. The first one is the date 2023-09-12 and then one item for every day until the current date
    dates = [
        dt.date(2023, 10, 16),
        dt.date(2023, 10, 17),
        dt.date(2023, 10, 18),
        dt.date(2023, 10, 19),
        dt.date(2023, 10, 20),
    ]

    dates = [
        {
            "value": date,
            "pre_display": f"Day {i+1}",
            "display": date,
            "count": DjangoConUS23Post.objects.filter(
                visibility="public",
                created_at__gte=date,
                created_at__lt=date + dt.timedelta(days=1),
            ).count(),
        }
        for i, date in enumerate(dates)
        if date <= dt.date.today()
    ]
    paginator = Paginator(posts, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    stats = DjangoConUS23Post.objects.filter(
        visibility="public",
        created_at__lte=dt.date(2023, 10, 20),
        created_at__gte=dt.date(2023, 10, 16),
    ).aggregate(
        total_posts=Count("id"),
        total_favourites=Sum("favourites_count"),
    )
    return render(
        request,
        "djangoconus.html",
        {
            "page_title": "FediDevs POSTS on DjangoCon US | Most Favourited Mastodon Posts about DjangoCon US",
            "page_header": "FEDIDEVS",
            "page_subheader": "DjangoCon US 2023 🐂",
            "page_description": "Most Favourited Mastodon Posts about DjangoCon US. Updated daily.",
            "page_image": "og-posts.png",
            "posts": page_obj,
            "total_posts": stats["total_posts"],
            "total_favourites": stats["total_favourites"],
            "posts_date": date,
            "dates": dates,
            "order": order,
        },
    )
