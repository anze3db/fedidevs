from django.core.paginator import Paginator
from django.views.decorators.cache import cache_page
from django.shortcuts import render

from .models import Account, LANGUAGES


@cache_page(60 * 60 * 24)
def index(request, lang=None):
    if lang not in [l.code for l in LANGUAGES]:
        lang = None
    if not lang:
        accounts = Account.objects.none()
    else:
        accounts = Account.objects.filter(note__contains=lang).order_by(
            "-followers_count"
        )
    paginator = Paginator(accounts, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "index.html",
        {
            "accounts": page_obj,
            "lang": lang,
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
