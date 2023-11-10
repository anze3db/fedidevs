import datetime as dt

from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import render
from django.utils import timezone

from confs.models import DjangoConAfricaAccount, DjangoConAfricaPost, Fwd50Account, Fwd50Post


# Create your views here.
def fwd50(request, date: dt.date | None = None):
    search_query = Q(
        visibility="public",
    )
    order = request.GET.get("order")
    if order not in ("-favourites_count", "-reblogs_count", "-replies_count", "-created_at"):
        order = "-favourites_count"

    if date:
        date = date.date()
        search_query &= Q(created_at__gte=date, created_at__lt=date + dt.timedelta(days=1))
    else:
        search_query &= Q()

    try:
        account_id = int(request.GET.get("account"))
    except (ValueError, TypeError):
        account_id = None
    if account_id:
        search_query &= Q(account_id=account_id)

    posts = Fwd50Post.objects.filter(search_query).order_by(order)
    # List of date objects. The first one is the date 2023-09-12 and then one item for every day until the current date
    dates = [
        dt.date(2023, 11, 6),
        dt.date(2023, 11, 7),
        dt.date(2023, 11, 8),
    ]

    users_with_most_posts = Fwd50Account.objects.filter().annotate(count=Count("posts")).order_by("-count")[:10]

    counts = (
        Fwd50Post.objects.filter(
            visibility="public",
            created_at__gte=min(dates),
            created_at__lt=max(dates) + dt.timedelta(days=1),
        )
        .values("created_at__date")
        .annotate(count=Count("id"))
    )
    counts_dict = {c["created_at__date"]: c["count"] for c in counts}

    dates = [
        {
            "value": date,
            "pre_display": f"Day {i+1}",
            "display": date,
            "count": counts_dict.get(date, 0),
        }
        for i, date in enumerate(dates)
        if date <= timezone.now().date()
    ]
    paginator = Paginator(posts, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    stats = Fwd50Post.objects.filter(
        visibility="public",
        # created_at__lte=dt.date(2023, 10, 20),
        # created_at__gte=dt.date(2023, 10, 16),
    ).aggregate(
        total_posts=Count("id"),
        total_favourites=Sum("favourites_count"),
    )
    return render(
        request,
        "fwd50.html",
        {
            "page_title": "Mastodon posts FWD50 | Most Favourited Mastodon Posts about FWD50",
            "page_header": "FWD50",
            "page_subheader": "Nov. 6-8, 2023 | Ottawa and online",
            "page_description": "Most Favourited Mastodon Posts about FWD50",
            "page_image": "og-fwd50.png",
            "posts": page_obj,
            "users_with_most_posts": users_with_most_posts,
            "total_posts": stats["total_posts"],
            "total_favourites": stats["total_favourites"],
            "posts_date": date,
            "dates": dates,
            "account_id": account_id,
            "order": order,
        },
    )


def djangoconafrica(request, date: dt.date | None = None):
    search_query = Q(
        visibility="public",
    )
    order = request.GET.get("order")
    if order not in ("-favourites_count", "-reblogs_count", "-replies_count", "-created_at"):
        order = "-favourites_count"

    if date:
        date = date.date()
        search_query &= Q(created_at__gte=date, created_at__lt=date + dt.timedelta(days=1))
    else:
        search_query &= Q()

    try:
        account_id = int(request.GET.get("account"))
    except (ValueError, TypeError):
        account_id = None
    if account_id:
        search_query &= Q(account_id=account_id)

    posts = DjangoConAfricaPost.objects.filter(search_query).order_by(order)
    # List of date objects. The first one is the date 2023-09-12 and then one item for every day until the current date
    dates = [
        dt.date(2023, 11, 7),
        dt.date(2023, 11, 8),
        dt.date(2023, 11, 9),
        dt.date(2023, 11, 10),
        dt.date(2023, 11, 11),
    ]

    users_with_most_posts = (
        DjangoConAfricaAccount.objects.filter().annotate(count=Count("posts")).order_by("-count")[:10]
    )

    # Tags is a JSON field with name and url, how to create a query to get all
    # distinct tag names from the posts table?
    tags = DjangoConAfricaPost.objects.filter().values("tags")
    # Flatten nested list of tags:
    tags = {tag["name"] for tags in tags for tag in tags["tags"]}

    selected_tag = request.GET.get("tag")
    if selected_tag in tags:
        search_query &= Q(tags__icontains=selected_tag)
    else:
        selected_tag = None

    counts = (
        DjangoConAfricaPost.objects.filter(
            visibility="public",
            created_at__gte=min(dates),
            created_at__lt=max(dates) + dt.timedelta(days=1),
        )
        .values("created_at__date")
        .annotate(count=Count("id"))
    )
    counts_dict = {c["created_at__date"]: c["count"] for c in counts}

    dates = [
        {
            "value": date,
            "pre_display": f"Day {i+1}",
            "display": date,
            "count": counts_dict.get(date, 0),
        }
        for i, date in enumerate(dates)
        if date <= timezone.now().date()
    ]
    paginator = Paginator(posts, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    stats = DjangoConAfricaPost.objects.filter(
        visibility="public",
        # created_at__lte=dt.date(2023, 10, 20),
        # created_at__gte=dt.date(2023, 10, 16),
    ).aggregate(
        total_posts=Count("id"),
        total_favourites=Sum("favourites_count"),
        total_reblogs=Sum("reblogs_count"),
    )
    return render(
        request,
        "djangoconafrica.html",
        {
            "page_title": "Mastodon posts | Most Favourited Mastodon Posts about #djangoconafrica",
            "page_header": "DjangoCon Africa",
            "page_subheader": "Nov 6 - 11, 2023 | Zanzibar, Tanzania",
            "page_description": "Most Favourited Mastodon Posts about #djangoconafrica",
            "page_image": "og-djangoconafrica.png",
            "posts": page_obj,
            "users_with_most_posts": users_with_most_posts,
            "stats": stats,
            "posts_date": date,
            "dates": dates,
            "account_id": account_id,
            "order": order,
            "tags": tags,
            "selected_tag": selected_tag,
        },
    )
