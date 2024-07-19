from django.core.paginator import Paginator
from django.db.models import Count, Exists, IntegerField, OuterRef, Q, Subquery
from django.shortcuts import render
from django.views.decorators.cache import cache_page

from mastodon_auth.models import AccountFollowing
from stats.models import WeeklyAccountChange

from .management.commands.crawler import INSTANCES
from .models import FRAMEWORKS, LANGUAGES, Account, AccountLookup


def index(request, lang: str | None = None):
    if "selected_instance" in request.GET:
        request.session["selected_instance"] = parse_instance(request.GET.get("selected_instance"))

    langs_map = {lng.code: lng for lng in LANGUAGES}
    frameworks_map = {f.code: f for f in FRAMEWORKS}

    # Get a dict of languages and their counts
    language_count_dict = {
        al["language"]: al["count"]
        for al in AccountLookup.objects.values("language").annotate(count=Count("language")).order_by("-count")
    }

    languages = (
        {
            "code": lng.code,
            "name": lng.name,
            "emoji": lng.emoji,
            "regex": lng.regex,
            "image": lng.image,
            "post_code": lng.post_code,
            "count": language_count_dict.get(lng.code, 0),
        }
        for lng in LANGUAGES
    )

    frameworks = (
        {
            "code": framework.code,
            "name": framework.name,
            "emoji": framework.emoji,
            "regex": framework.regex,
            "image": framework.image,
            "post_code": framework.post_code,
            "count": language_count_dict.get(framework.code, 0),
        }
        for framework in FRAMEWORKS
    )

    selected_lang = langs_map.get(lang)
    selected_framework = frameworks_map.get(lang)
    frameworks = sorted(
        frameworks,
        key=lambda framework: (framework["count"]),
        reverse=True,
    )
    languages = sorted(
        languages,
        key=lambda lng: lng["count"],
        reverse=True,
    )

    search_query = Q(discoverable=True, noindex=False)
    if selected_lang:
        search_query &= Q(accountlookup__language=selected_lang.code)
    if selected_framework:
        search_query &= Q(accountlookup__language=selected_framework.code)

    query = request.GET.get("q", "").strip()
    order = request.GET.get("o", "-followers_count")
    if order not in ("-followers_count", "url", "-last_status_at", "-statuses_count", "-new_followers"):
        order = "-followers_count"
    if query:
        search_query &= (
            Q(note__icontains=query)
            | Q(display_name__icontains=query)
            | Q(username__icontains=query)
            | Q(url__icontains=query)
        )

    # Annotate the Account model with weekly followers gained from WeeklyAccountChange
    weekly_followers_gained = (
        WeeklyAccountChange.objects.filter(account=OuterRef("pk")).order_by("-id").values("followers_count")[:1]
    )
    accounts = Account.objects.filter(search_query).annotate(
        new_followers=Subquery(weekly_followers_gained, output_field=IntegerField())
    )
    accounts = accounts.prefetch_related("accountlookup_set").order_by(order)
    if request.user.is_authenticated:
        # Annotate whether the current request user is following the account:
        accounts = accounts.annotate(
            is_following=Exists(
                AccountFollowing.objects.filter(account=request.user.accountaccess.account, url=OuterRef("url")),
            )
        )
    paginator = Paginator(accounts, 50)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    accounts_count = Account.objects.filter(discoverable=True, noindex=False).count()

    user_instance = None
    if request.user.is_authenticated:
        user_instance = str(request.user.accountaccess.instance)

    return render(
        request,
        "v2/accounts.html" if "HX-Request" in request.headers else "v2/index.html",
        {
            "page": "accounts",
            "page_title": "FediDevs | List of software developers on Mastodon"
            if not selected_lang
            else f"FediDevs | List of {selected_lang.name} developers on Mastodon",
            "page_header": "FEDIDEVS",
            "page_subheader": "",
            "page_description": "Discover amazing developers from across the Fediverse."
            if not selected_lang
            else f"Discover amazing {selected_lang.name} developers from across the fediverse.",
            "page_image": "og.png",
            "accounts": page_obj,
            "selected_lang": selected_lang,
            "selected_framework": selected_framework,
            "selected_lang_or_framework": selected_lang or selected_framework,
            "languages": languages,
            "frameworks": frameworks,
            "instances": INSTANCES,
            "instances_count": len(INSTANCES),
            "accounts_count": accounts_count,  # TODO might be slow
            "selected_instance": request.session.get("selected_instance") or user_instance,
            "query": query,
            "order": order,
            "user": request.user,
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
            "frameworks": FRAMEWORKS,
        },
    )


@cache_page(60 * 60 * 24, cache="memory")
def devs_on_mastodon(request):
    all_devs = Account.objects.values("instance").annotate(count=Count("instance")).order_by("-count")[:10]
    by_language_devs = (
        Account.objects.values("instance", "accountlookup__language")
        .filter(accountlookup__language__in=["python", "javascript", "ruby", "php", "rust"])
        .annotate(count=Count("instance"))
        .order_by("-count")
    )
    by_python_devs = [i for i in by_language_devs if i["accountlookup__language"] == "python"][:10]
    by_javascript_devs = [i for i in by_language_devs if i["accountlookup__language"] == "javascript"][:10]
    by_ruby_devs = [i for i in by_language_devs if i["accountlookup__language"] == "ruby"][:10]
    by_php_devs = [i for i in by_language_devs if i["accountlookup__language"] == "php"][:10]
    by_rust_devs = [i for i in by_language_devs if i["accountlookup__language"] == "rust"][:10]

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
