import datetime as dt

from django.core.paginator import Paginator
from django.db.models import Count, F, Q, Sum
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from confs.models import (
    Conference,
    DjangoConAfricaAccount,
    DjangoConAfricaPost,
    DotNetConfAccount,
    DotNetConfPost,
    Fwd50Account,
    Fwd50Post,
)


def conferences(request):
    today = timezone.now().date()
    upcoming_conferences = Conference.objects.filter(start_date__gt=today).order_by("start_date")
    live_conferences = Conference.objects.filter(start_date__lte=today, end_date__gte=today).order_by("start_date")
    past_conferences = Conference.objects.filter(end_date__lt=today).order_by("-start_date")

    return render(
        request,
        "conferences.html",
        {
            "page_title": "Conferences | Fediverse Developers",
            "page_header": "CONFERENCES",
            "page_subheader": "",
            "page_description": "",
            "page_image": "og-conferences.png",
            "is_superuser": request.user.is_superuser,
            "upcoming_conferences": upcoming_conferences,
            "live_conferences": live_conferences,
            "past_conferences": past_conferences,
        },
    )


def conference(request, slug: str):
    conference = get_object_or_404(Conference, slug=slug)
    if conference.posts_after:
        search_query = Q(created_at__gte=conference.posts_after)
    else:
        search_query = Q()
    order = request.GET.get("order")

    try:
        account_id = int(request.GET.get("account"))
    except (ValueError, TypeError):
        account_id = None
    if account_id:
        search_query &= Q(account_id=account_id)

    all_conf_posts_count = conference.posts.filter(search_query).count()

    date = request.GET.get("date")
    if date and (date := parse_date(date)):
        search_query &= Q(created_at__gte=date, created_at__lt=date + dt.timedelta(days=1))

    if order not in ("-favourites_count", "-reblogs_count", "-replies_count", "-created_at"):
        if date:
            order = "-favourites_count"
        else:
            order = "-created_at"

    counts = (
        conference.posts.filter(
            visibility="public",
            created_at__gte=conference.start_date,
            created_at__lt=conference.end_date + dt.timedelta(days=1),
        )
        .values("created_at__date")
        .annotate(count=Count("id"))
    )
    counts_dict = {c["created_at__date"]: c["count"] for c in counts}
    dates = [
        conference.start_date + dt.timedelta(days=i)
        for i in range((conference.end_date - conference.start_date).days + 1)
    ]
    dates = [
        {
            "value": date,
            "pre_display": f"Day {i+1}",
            "display": date,
            "count": counts_dict.get(date, 0),
        }
        for i, date in enumerate(dates)
    ]

    posts = (
        conference.posts.filter(search_query).order_by(order).prefetch_related("account", "account__accountlookup_set")
    )
    if conference.posts_after:
        accounts = conference.accounts.filter(post__created_at__gt=conference.posts_after)
    else:
        accounts = conference.accounts.all()

    accounts = accounts.annotate(
        count=Count("conference__posts", filter=Q(conference__posts__account=F("pk"), conference=conference))
    ).order_by("-count")[:10]

    paginator = Paginator(posts, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    return render(
        request,
        "conference.html",
        {
            "page_title": f"{conference.name} | Fediverse Developers",
            "page_header": conference.name,
            "page_subheader": f"{conference.start_date.strftime('%b %d')} - {conference.end_date.strftime('%b %d, %Y')}",
            "page_description": "Aggregated posts from the Fediverse about " + conference.name,
            "page_image": "og-conferences.png",
            "page_url": reverse("conference", kwargs={"slug": conference.slug}),
            "conference": conference,
            "posts": page_obj,
            "accounts": accounts,
            "slug": slug,
            "post_date": date,
            "account_id": account_id,
            "dates": dates,
            "all_conf_posts_count": all_conf_posts_count,
            "posts_date": date,
            "order": order,
            "is_superuser": request.user.is_superuser,
        },
    )


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

    tags = DjangoConAfricaPost.objects.filter().values("tags")
    tags = {tag["name"] for tags in tags for tag in tags["tags"]}

    selected_tag = request.GET.get("tag")
    if selected_tag in tags:
        search_query &= Q(tags__icontains=f'"name": "{selected_tag}"')
    else:
        selected_tag = None

    posts = DjangoConAfricaPost.objects.filter(search_query).prefetch_related("account").order_by(order)
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
            "tags": sorted(tags),
            "selected_tag": selected_tag,
        },
    )


def dotnetconf(request, date: dt.date | None = None):
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
        search_query &= Q(
            created_at__gte=dt.date(2023, 11, 1),
        )

    try:
        account_id = int(request.GET.get("account"))
    except (ValueError, TypeError):
        account_id = None
    if account_id:
        search_query &= Q(account_id=account_id)

    tags = DotNetConfPost.objects.filter().values("tags")
    tags = {tag["name"] for tags in tags for tag in tags["tags"]}

    selected_tag = request.GET.get("tag")
    if selected_tag in tags:
        search_query &= Q(tags__icontains=f'"name": "{selected_tag}"')
    else:
        selected_tag = None

    posts = DotNetConfPost.objects.filter(search_query).prefetch_related("account").order_by(order)
    # List of date objects. The first one is the date 2023-09-12 and then one item for every day until the current date
    dates = [
        dt.date(2023, 11, 14),
        dt.date(2023, 11, 15),
        dt.date(2023, 11, 16),
    ]

    users_with_most_posts = (
        DotNetConfAccount.objects.filter(posts__created_at__gte=dt.date(2023, 11, 1))
        .annotate(count=Count("posts"))
        .order_by("-count")[:10]
    )

    counts = (
        DotNetConfPost.objects.filter(
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

    stats = DotNetConfPost.objects.filter(
        visibility="public",
        # created_at__lte=dt.date(2023, 10, 20),
        created_at__gte=dt.date(2023, 11, 1),
    ).aggregate(
        total_posts=Count("id"),
        total_favourites=Sum("favourites_count"),
        total_reblogs=Sum("reblogs_count"),
    )
    return render(
        request,
        "dotnetcon.html",
        {
            "page_title": ".NET Conf 2023 | Most Favourited Mastodon Posts about .NET Conf 2023",
            "page_header": ".NET Conf 2023",
            "page_subheader": "Nov 14-16, 2023",
            "page_description": "Most Favourited Mastodon Posts about #dotnetconf",
            "page_image": "og-dotnetconf.png",
            "posts": page_obj,
            "users_with_most_posts": users_with_most_posts,
            "stats": stats,
            "posts_date": date,
            "dates": dates,
            "account_id": account_id,
            "order": order,
            "tags": sorted(tags),
            "selected_tag": selected_tag,
        },
    )
