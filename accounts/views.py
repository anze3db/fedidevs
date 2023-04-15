from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .management.commands.crawler import INSTANCES
from .models import LANGUAGES, Account


def index(request, lang: str | None = None):
    langs_map = {l.code: l for l in LANGUAGES}
    selected_lang = langs_map.get(lang) or LANGUAGES[0]
    search_query = Q()
    if selected_lang:
        search_query = Q(accountlookup__language=selected_lang.code)

    query = request.GET.get("q", "")
    order = request.GET.get("o", "-followers_count")
    if order not in ("-followers_count", "url", "-last_status_at", "-statuses_count"):
        order = "-followers_count"
    if query:
        search_query &= (
            Q(note__icontains=query)
            | Q(display_name__icontains=query)
            | Q(username__icontains=query)
            | Q(url__icontains=query)
        )

    accounts = Account.objects.filter(search_query).order_by(order)
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
            "instances": INSTANCES,
            "selected_instance": request.session.get("selected_instance"),
            "query": query,
            "order": order,
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


def faq(request):
    return render(request, "faq.html", {"instances": INSTANCES, "languages": LANGUAGES})


@require_http_methods(["POST"])
def instance(request):
    request.session["selected_instance"] = request.POST.get("instance")
    return redirect("empty-index")
