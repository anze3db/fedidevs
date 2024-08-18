import json

from django.shortcuts import render

from accounts.models import FRAMEWORKS, LANGUAGES
from stats.models import Daily

GRAPH_DAYS_LEN = 30


def stats(request):
    cards = []
    daily_objects = Daily.objects.order_by("-date")[:GRAPH_DAYS_LEN]
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
        if start_count < end_count:
            card["percent_change"] = round((end_count - start_count) / start_count * 100, 1)
        if start_count > end_count:
            card["percent_change"] = round(- ((start_count - end_count) / start_count * 100), 2)

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
            "cards": cards,                   # Needed for template rendering
            "cards_json": json.dumps(cards),  # Needed for JavaScript parsing
        },
    )
