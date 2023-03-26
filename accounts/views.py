from django.core.paginator import Paginator
from django.shortcuts import render

from .models import LANGUAGES, Account


def index(request, lang: str | None = None):
    langs_map = {l.code: l for l in LANGUAGES}
    selected_lang = langs_map.get(lang) or LANGUAGES[0]
    if not selected_lang:
        accounts = Account.objects.none()
    else:
        accounts = Account.objects.filter(
            accountlookup__language=selected_lang.code
        ).order_by("-followers_count")
    paginator = Paginator(accounts, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "index.html",
        {
            "accounts": page_obj,
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
