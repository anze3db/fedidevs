import datetime as dt
from textwrap import dedent

from django import forms
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from posts.models import DjangoConUS23Post, PostSubscription


def djangoconus(request, date: dt.date | None = None):
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

    counts = (
        DjangoConUS23Post.objects.filter(
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
            "pre_display": f"Talks: Day {i+1}" if i < 3 else f"Sprints: Day {i-2}",
            "display": date,
            "count": counts_dict.get(date, 0),
        }
        for i, date in enumerate(dates)
        if date <= timezone.now().date()
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
            "page_image": "og-djangoconus23.png",
            "posts": page_obj,
            "total_posts": stats["total_posts"],
            "total_favourites": stats["total_favourites"],
            "posts_date": date,
            "dates": dates,
            "order": order,
        },
    )


class SubscribeForm(forms.ModelForm):
    framework_or_lang = forms.CharField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = PostSubscription
        fields = ["email", "framework_or_lang"]


def subscribe(request):
    if request.method == "POST":
        form = SubscribeForm(request.POST)
        if form.is_valid():
            form.save()
            send_mail(
                "Fedidevs new subscriber!",
                dedent(
                    f"""
                    New subscriber with email {form.cleaned_data["email"]}.
                    Framework or lang: {form.cleaned_data["framework_or_lang"]}
                """
                ),
                "anze@fedidevs.com",
                ["anze@pecar.me"],
                fail_silently=True,
            )
            return redirect("posts_subscribe_success")
        else:
            return render(request, "subscribe.html", {"form": form})
    return render(
        request,
        "subscribe.html",
        {
            "form": SubscribeForm(),
            "page_title": "Fedidevs Subscribe to Daily Posts",
            "page_header": "FEDIDEVS",
            "page_subheader": "Subscribe to Daily Posts"
            + (" on " + request.POST.get("framework_or_lang") if request.POST.get("framework_or_lang") else ""),
        },
    )


def subscribe_success(request):
    return render(
        request,
        "subscribe_success.html",
        {
            "form": SubscribeForm(),
            "page_title": "Subscribed 🎉",
            "page_header": "FEDIDEVS",
            "page_subheader": "",
        },
    )
