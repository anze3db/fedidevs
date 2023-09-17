from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import render
from django.views.decorators.cache import cache_page

from .management.commands.crawler import INSTANCES
from .models import LANGUAGES, Account


def index(request, lang: str | None = None):
    if "selected_instance" in request.GET:
        request.session["selected_instance"] = parse_instance(
            request.GET.get("selected_instance")
        )

    langs_map = {l.code: l for l in LANGUAGES}
    selected_lang = langs_map.get(lang)
    search_query = Q()
    if selected_lang:
        search_query = Q(accountlookup__language=selected_lang.code)

    query = request.GET.get("q", "").strip()
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

    accounts = (
        Account.objects.filter(search_query)
        .prefetch_related("accountlookup_set")
        .order_by(order)
    )
    paginator = Paginator(accounts, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    accounts_count = Account.objects.filter(discoverable=True, noindex=False).count()

    return render(
        request,
        "index.html",
        {
            "page_title": "FediDevs | List of software developers on Mastodon"
            if not selected_lang
            else f"FediDevs | List of {selected_lang.name} developers on Mastodon",
            "page_header": "FEDIDEVS",
            "page_subheader": f'Discover <mark>{accounts_count}</mark> superb devs from across the <a style="color: var(--pico-h1-color);" href="/developers-on-mastodon/" data-tooltip="{len(INSTANCES)} Mastodon instances indexed">Fediverse</a>',
            "page_description": "Discover amazing developers from across the Fediverse."
            if not selected_lang
            else f"Discover amazing {selected_lang.name} developers from across the fediverse.",
            "page_image": "og.png",
            "accounts": page_obj,
            "selected_lang": selected_lang,
            "languages": LANGUAGES,
            "instances": INSTANCES,
            "instances_count": len(INSTANCES),
            "accounts_count": accounts_count,  # TODO might be slow
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


@cache_page(60 * 60 * 24, cache="memory")
def faq(request):
    return render(
        request,
        "faq.html",
        {
            "page_title": "FediDevs | FAQ",
            "page_header": "FEDIDEVS FAQ",
            "page_description": "Frequently Asked Questions",
            "page_image": "faq.png",
            "instances": INSTANCES,
            "languages": LANGUAGES,
        },
    )


@cache_page(60 * 60 * 24, cache="memory")
def devs_on_mastodon(request):
    all_devs = (
        Account.objects.values("instance")
        .annotate(count=Count("instance"))
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
        "mastodon_instances.html",
        {
            "page_title": "FediDevs | Mastodon instances with software developers",
            "page_header": "FEDIDEVS",
            "page_description": "Which Mastodon instances have the most software developer accounts.",
            "page_image": "devs-on-mastodon.png",
            "all_devs": all_devs,
            "python_devs": by_python_devs,
            "ruby_devs": by_ruby_devs,
            "php_devs": by_php_devs,
            "rust_devs": by_rust_devs,
            "javascript_devs": by_javascript_devs,
        },
    )


def parse_instance(instance: str | None):
    if not instance:
        return None
    if "." not in instance:
        return None
    return instance.replace("https://", "").replace("http://", "").replace("/", "")
