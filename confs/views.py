import datetime as dt
from typing import Literal

from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.cache import cache_page

from accounts.views import build_canonical_url
from confs.models import (
    FRAMEWORKS,
    LANGUAGES,
    Conference,
    ConferenceAccount,
    ConferenceLookup,
    ConferencePost,
    DjangoConAfricaAccount,
    DjangoConAfricaPost,
    DotNetConfAccount,
    DotNetConfPost,
    Fwd50Account,
    Fwd50Post,
)


def conferences(request, lang: str | None = None):
    language_count_dict = {
        al["language"]: al["count"]
        for al in ConferenceLookup.objects.values("language").annotate(count=Count("language")).order_by("-count")
    }

    languages = (
        {
            "code": lng.code,
            "name": lng.name,
            "emoji": lng.emoji,
            "regex": lng.regex,
            "image": lng.image,
            "post_code": lng.post_code,
            "count": language_count_dict.get(lng.code, 0),
        }
        for lng in LANGUAGES
    )

    frameworks = (
        {
            "code": framework.code,
            "name": framework.name,
            "emoji": framework.emoji,
            "regex": framework.regex,
            "image": framework.image,
            "post_code": framework.post_code,
            "count": language_count_dict.get(framework.code, 0),
        }
        for framework in FRAMEWORKS
    )

    langs_map = {lng.code: lng for lng in LANGUAGES}
    frameworks_map = {f.code: f for f in FRAMEWORKS}

    selected_lang = langs_map.get(lang)
    selected_framework = frameworks_map.get(lang)
    search_query = Q()
    if selected_lang:
        search_query &= Q(conferencelookup__language=selected_lang.code)
    if selected_framework:
        search_query &= Q(conferencelookup__language=selected_framework.code)

    today = timezone.now().date()
    upcoming_conferences = (
        Conference.objects.filter(start_date__gt=today)
        .prefetch_related("conferencelookup_set")
        .annotate(posts_count=Count("posts"))
        .filter(search_query)
        .order_by("start_date")
    )
    live_conferences = (
        Conference.objects.filter(start_date__lte=today, end_date__gte=today)
        .filter(search_query)
        .prefetch_related("conferencelookup_set")
        .annotate(posts_count=Count("posts"))
        .order_by("start_date")
    )
    past_conferences = (
        Conference.objects.filter(end_date__lt=today)
        .prefetch_related("conferencelookup_set")
        .annotate(posts_count=Count("posts"))
        .filter(search_query)
        .order_by("-start_date")
    )

    frameworks = sorted(
        [f for f in frameworks if f["count"] > 0],
        key=lambda framework: (framework["count"]),
        reverse=True,
    )
    languages = sorted(
        [lang for lang in languages if lang["count"] > 0],
        key=lambda lng: lng["count"],
        reverse=True,
    )
    return render(
        request,
        "conferences.html",
        {
            "page_title": "Conferences | Fediverse Developers",
            "page": "conferences",
            "page_header": "Conferences",
            "page_subheader": "",
            "page_description": "",
            "page_image": "og-conferences.png",
            "is_superuser": request.user.is_superuser,
            "upcoming_conferences": upcoming_conferences,
            "live_conferences": live_conferences,
            "past_conferences": past_conferences,
            "languages": languages,
            "frameworks": frameworks,
            "selected_lang": selected_lang,
            "selected_framework": selected_framework,
        },
    )


def get_order_display(order: Literal["-favourites_count", "-reblogs_count", "-replies_count", "-created_at"]):
    match order:
        case "-favourites_count":
            return "Favorites"
        case "-reblogs_count":
            return "Boosts"
        case "-replies_count":
            return "Replies"
        case "-created_at":
            return "Created Date"


@cache_page(30, cache="memory")
def conference(request, slug: str):
    conference = get_object_or_404(Conference, slug=slug)
    if conference.posts_after:
        search_query = Q(conference=conference, created_at__gte=conference.posts_after)
    else:
        search_query = Q(
            conference=conference,
        )

    order = request.GET.get("o")
    if not order:
        order = request.GET.get("order")

    try:
        account_id = int(request.GET.get("account"))
    except (ValueError, TypeError):
        account_id = None
    if account_id:
        search_query &= Q(account_id=account_id)

    date = request.GET.get("date") or None
    if date and (date := parse_date(date)):
        search_query &= Q(created_at__gte=date, created_at__lt=date + dt.timedelta(days=1))

    all_conf_posts_count = ConferencePost.objects.filter(search_query).count()
    if order not in ("-favourites_count", "-reblogs_count", "-replies_count", "-created_at"):
        if conference.start_date <= timezone.now().date() <= conference.end_date:
            order = "-created_at"
        else:
            order = "-favourites_count"

    counts = (
        ConferencePost.objects.filter(
            conference=conference,
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
    if conference.days.strip():
        day_names = {i: n.strip() for i, n in enumerate(conference.days.strip().split(","))}
    else:
        day_names = {}
    if conference.day_styles.strip():
        day_styles = {i: s.strip() for i, s in enumerate(conference.day_styles.strip().split(","))}
    else:
        day_styles = {}
    dates = [
        {
            "value": date,
            "pre_display": f"Day {i + 1}" + (f": {day_names[i]}" if day_names.get(i) else ""),
            "display": date,
            "day_style": day_styles.get(i, ""),
            "count": counts_dict.get(date, 0),
        }
        for i, date in enumerate(dates)
    ]
    conf_posts = (
        ConferencePost.objects.filter(search_query)
        .order_by(order)
        .prefetch_related("post", "post__account", "post__account__accountlookup", "post__account__instance_model")
    )

    account_counts = (
        ConferenceAccount.objects.filter(conference=conference)
        .select_related("account")
        .filter(count__gt=0)
        .order_by("-count")[:10]
    )

    paginator = Paginator(conf_posts, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    user_instance = None
    if request.user.is_authenticated:
        user_instance = str(request.user.accountaccess.instance)

    current_account = next((account for account in account_counts if account.account.id == account_id), None)
    current_date = next((d for d in dates if d["value"] == date), None)
    if all_conf_posts_count > 0:
        page_description = f"Dive into {all_conf_posts_count} insightful Mastodon posts from {conference.name} {conference.start_date.strftime('%Y')}"
        if current_account:
            page_description += f" by {current_account.account.name}"
        if current_date:
            page_description += f" on {current_date['pre_display']}"
        page_description += " featuring key discussions, trending topics, and highlights from the conference."
    else:
        page_description = f"Explore Mastodon posts about {conference.name} {conference.start_date.strftime('%Y')}"

    return render(
        request,
        "conference.html" if "HX-Request" not in request.headers else "conference.html#posts-partial",
        {
            "page_title": f"{conference.name}: Explore {ConferencePost.objects.filter(conference=conference).count()} Mastodon Posts & Conference Highlights",
            "page": "conferences",
            # Conference header is conference.name and year
            "page_header": conference.name + " " + conference.start_date.strftime("%Y"),
            "page_header_color": "red",
            "primary_tag": next(tag for tag in conference.tags.split(",") if tag),
            "page_subheader": f"{conference.start_date.strftime('%b %d')} - {conference.end_date.strftime('%b %d, %Y')}",
            "page_description": page_description,
            "canonical_url": build_canonical_url(
                reverse("conference", kwargs={"slug": conference.slug}), request.GET, ["account", "date"]
            ),
            "page_image": "og-conferences.png",
            "page_url": reverse("conference", kwargs={"slug": conference.slug}),
            "conference": conference,
            "conf_posts": page_obj,
            "account_counts": account_counts,
            "selected_instance": user_instance,
            "slug": slug,
            "account_id": account_id,
            "current_account": current_account,
            "order_display": get_order_display(order),
            "dates": dates,
            "all_conf_posts_count": all_conf_posts_count,
            "posts_date": date,
            "current_date": current_date,
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
            "page": "conferences",
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
            "page": "conferences",
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
            "page": "conferences",
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
