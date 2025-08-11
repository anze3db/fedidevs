import json

from django.shortcuts import render
from django.templatetags.static import static

from accounts.models import FRAMEWORKS, LANGUAGES
from stats.models import Daily


def stats(request):
    period = request.GET.get("p") or "weekly"
    if period == "weekly":
        graph_days_len = 7
        period_name = "week"
    elif period == "biweekly":
        graph_days_len = 14
        period_name = "two weeks"
    elif period == "monthly":
        graph_days_len = 30
        period_name = "month"
    else:
        graph_days_len = 7
        period_name = "week"

    cards = []
    values = [f"{lang.code}_accounts" for lang in (LANGUAGES + FRAMEWORKS)] + ["date"]
    daily_objects = Daily.objects.order_by("-date").values(*values)[:graph_days_len]
    if daily_objects:
        for lang in LANGUAGES + FRAMEWORKS:
            card = {
                "code": lang.code,
                "name": lang.name,
                "emoji": lang.emoji,
                "image": lang.image,
                "accounts_count": [],
                "dates": [],
                "percent_change": 0,
                "total_accounts": 0,
            }

            for daily in reversed(daily_objects):
                card["accounts_count"].append(daily[f"{lang.code}_accounts"])
                card["dates"].append(daily["date"].strftime("%Y-%m-%d"))

            start_count = card["accounts_count"][0]
            end_count = card["accounts_count"][-1]
            if start_count == 0:
                card["percent_change"] = 0
            elif start_count < end_count:
                card["percent_change"] = round((end_count - start_count) / start_count * 100, 1)
            elif start_count > end_count:
                card["percent_change"] = round(-((start_count - end_count) / start_count * 100), 2)
            card["count_diff"] = end_count - start_count
            card["total_accounts"] = end_count

            cards.append(card)

    order = request.GET.get("o") or "percent_change"
    if order not in ("percent_change", "count", "name", "count_diff"):
        order = "count"

    cards = sorted(cards, key=lambda x: x[order], reverse=True)

    return render(
        request,
        "stats.html",
        {
            "page_title": "Stats | Fedidevs",
            "page": "stats",
            "page_header": "Stats",
            "page_subheader": "See how many developers on Mastodon are using your favorite languages and frameworks.",
            "page_description": "Stats on the number of developers on Mastodon using various programming languages and frameworks.",
            "page_image": static("og-stats.png"),
            "period_name": period_name,
            "cards": cards,  # Needed for template rendering
            "cards_json": json.dumps(cards),  # Needed for JavaScript parsing
            "period_display_name": f"Last {graph_days_len} days",
        },
    )
