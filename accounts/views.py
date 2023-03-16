from django.core.paginator import Paginator
from django.shortcuts import render

from .models import Account

LANGUAGES = ("python", "javascript", "ruby", "rust", "golang", "php")
LANG_EMOJI = ("🐍", "📜", "💎", "🦀", "🐹", "🐘")


def index(request, lang=None):
    if lang not in LANGUAGES:
        lang = ""
    accounts = Account.objects.filter(note__contains=lang).order_by("-followers_count")
    paginator = Paginator(accounts, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "index.html",
        {"accounts": page_obj, "lang": lang, "languages": zip(LANGUAGES, LANG_EMOJI)},
    )
