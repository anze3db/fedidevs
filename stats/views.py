import json

from django.shortcuts import render

from accounts.models import FRAMEWORKS, LANGUAGES
from stats.models import Daily


def stats(request):
    period = request.GET.get("p") or "weekly"
    if period == "weekly":
        graph_days_len = 7
        period_name = "seven"
    elif period == "biweekly":
        graph_days_len = 14
        period_name = "fourteen"
    elif period == "monthly":
        graph_days_len = 30
        period_name = "thirty"
    else:
        graph_days_len = 7
        period_name = "seven"

    cards = []
    values = [f"{lang.code}_accounts" for lang in (LANGUAGES + FRAMEWORKS)] + ["date"]
    daily_objects = Daily.objects.order_by("-date").values(*values)[:graph_days_len]
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
            card["percent_change"] = "N/A"
        elif start_count < end_count:
            card["percent_change"] = round((end_count - start_count) / start_count * 100, 1)
        elif start_count > end_count:
            card["percent_change"] = round(-((start_count - end_count) / start_count * 100), 2)

        card["total_accounts"] = end_count

        cards.append(card)

    return render(
        request,
        "stats.html",
        {
            "page_title": "Statistics | Fediverse Developers",
            "page": "stats",
            "page_header": "Stats",
            "page_subheader": "See how many developers on Mastodon are using your favorite languages and frameworks.",
            "page_description": "Statistics on the number of developers on Mastodon using various programming languages and frameworks.",
            "page_image": "og-stats.png",
            "period_name": period_name,
            "cards": cards,  # Needed for template rendering
            "cards_json": json.dumps(cards),  # Needed for JavaScript parsing
            "period_display_name": f"Last {graph_days_len} days",
        },
    )
