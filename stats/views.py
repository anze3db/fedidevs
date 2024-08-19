import json

from django.shortcuts import render

from accounts.models import FRAMEWORKS, LANGUAGES
from stats.models import Daily


def stats(request):
    period = request.GET.get("p") or "monthly"
    if period == "weekly":
        graph_days_len = 7
        period_display_name = "Last 7 days"
    elif period == "monthly":
        graph_days_len = 30
        period_display_name = "Last 30 days"
    elif period == "trimonthly":
        graph_days_len = 90
        period_display_name = "Last 90 days"

    cards = []
    daily_objects = Daily.objects.order_by("-date")[:graph_days_len]
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
            card["accounts_count"].append(getattr(daily, f"{lang.code}_accounts"))
            card["dates"].append(daily.date.strftime("%Y-%m-%d"))

        start_count = getattr(daily_objects[len(daily_objects) - 1], f"{lang.code}_accounts")
        end_count = getattr(daily_objects[0], f"{lang.code}_accounts")
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
            "page_header": "Statistics",
            "page_subheader": "",
            "page_description": "",
            "page_image": "og.png",
            "cards": cards,  # Needed for template rendering
            "cards_json": json.dumps(cards),  # Needed for JavaScript parsing
            "period_display_name": period_display_name,
        },
    )
