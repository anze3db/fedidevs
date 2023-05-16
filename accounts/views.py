from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .management.commands.crawler import INSTANCES
from .models import LANGUAGES, Account


def index(request, lang: str | None = None):
    langs_map = {l.code: l for l in LANGUAGES}
    selected_lang = langs_map.get(lang)
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
    paginator = Paginator(accounts, 10)
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
            "instances_count": len(INSTANCES),
            "accounts_count": Account.objects.filter(
                discoverable=True, noindex=False
            ).count(),  # TODO might be slow
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


def devs_on_mastodon(request):
    all_devs = (
        Account.objects.values("instance").annotate(count=Count("instance"))
        # .filter(
        #     accountlookup__language__in=["python", "javascript", "ruby", "php", "rust"]
        # )
        .order_by("-count")[:10]
    )
    by_language_devs = (
        Account.objects.values("instance", "accountlookup__language")
        .filter(
            accountlookup__language__in=["python", "javascript", "ruby", "php", "rust"]
        )
        .annotate(count=Count("instance"))
        .order_by("-count")
    )
    by_python_devs = [
        i for i in by_language_devs if i["accountlookup__language"] == "python"
    ][:10]
    by_javascript_devs = [
        i for i in by_language_devs if i["accountlookup__language"] == "javascript"
    ][:10]
    by_ruby_devs = [
        i for i in by_language_devs if i["accountlookup__language"] == "ruby"
    ][:10]
    by_php_devs = [
        i for i in by_language_devs if i["accountlookup__language"] == "php"
    ][:10]
    by_rust_devs = [
        i for i in by_language_devs if i["accountlookup__language"] == "rust"
    ][:10]

    return render(
        request,
        "devs_on_mastodon.html",
        {
            "all_devs": all_devs,
            "python_devs": by_python_devs,
            "ruby_devs": by_ruby_devs,
            "php_devs": by_php_devs,
            "rust_devs": by_rust_devs,
            "javascript_devs": by_javascript_devs,
            "page_title": "Software Developers on Mastodon | 👩‍💻 FediDevs 🧑‍💻",
        },
    )


@require_http_methods(["POST"])
def instance(request):
    request.session["selected_instance"] = request.POST.get("instance")
    return redirect("empty-index")
