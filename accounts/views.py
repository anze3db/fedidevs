from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Q
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import cache_page

from mastodon_auth.models import AccountFollowing
from stats.models import Daily

from .models import FRAMEWORKS, LANGUAGES, Account, AccountLookup, Instance


def get_lookup_sort_order(order: str, period: str):
    prefix = "-accountlookup__"
    if order == "last_status_at":
        return f"{prefix}last_status_at"

    if order not in (
        "followers",
        "statuses",
    ) or period not in (
        "daily",
        "weekly",
        "monthly",
        "all",
    ):
        return f"{prefix}followers_count"

    if period == "all":
        return f"{prefix}{order}_count"

    return f"{prefix}{period}_{order}_count"


def get_display_strings(order: str, period: str):
    res = {}
    if order == "last_status_at":
        res["order"] = "Date of Last Post"
    elif order == "statuses":
        res["order"] = "Posts"
    else:
        res["order"] = "Followers"

    if period == "daily":
        res["period"] = "Last day"
    elif period == "weekly":
        res["period"] = "Last 7 days"
    elif period == "monthly":
        res["period"] = "Last 30 days"
    else:
        res["period"] = "All time"

    return res


def index(request, lang: str | None = None):
    if "selected_instance" in request.GET:
        request.session["selected_instance"] = parse_instance(request.GET.get("selected_instance"))

    langs_map = {lng.code: lng for lng in LANGUAGES}
    frameworks_map = {f.code: f for f in FRAMEWORKS}

    # Get a dict of languages and their counts
    language_counts = Daily.objects.order_by("date").last()
    if language_counts:
        language_count_dict = {
            lang.code: getattr(language_counts, f"{lang.code}_accounts") for lang in LANGUAGES + FRAMEWORKS
        }
    else:
        language_count_dict = {}
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

    search_query = Q(accountlookup__isnull=False)
    if selected_lang:
        search_query &= Q(accountlookup__language__icontains=selected_lang.code)
    if selected_framework:
        search_query &= Q(accountlookup__language__icontains=selected_framework.code)

    order = request.GET.get("o") or "followers"
    period = request.GET.get("p") or "all"
    query = request.GET.get("q", "").strip()

    account_type = request.GET.get("t")
    if account_type == "human":
        search_query &= Q(accountlookup__account_type="H")
    elif account_type == "project":
        search_query &= Q(accountlookup__account_type="P")
    elif account_type == "unknown":
        search_query &= Q(accountlookup__account_type="U")

    show_period_dropdown = order != "last_status_at"
    sort_order = get_lookup_sort_order(order, period)
    if query:
        search_query &= Q(accountlookup__text__icontains=query)

    # Annotate the Account model with weekly followers gained from WeeklyAccountChange
    accounts = Account.objects.select_related("accountlookup", "instance_model").filter(search_query)
    accounts = accounts.order_by(sort_order)
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
    accounts_count = AccountLookup.objects.filter().count()

    user_instance = None
    if request.user.is_authenticated:
        user_instance = str(request.user.accountaccess.instance)

    instances = Instance.objects.values_list("instance", flat=True)

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
            "instances": instances,
            "account_type": account_type,
            "instances_count": len(instances),
            "accounts_count": accounts_count,  # TODO might be slow
            "selected_instance": request.session.get("selected_instance") or user_instance,
            "query": query,
            "sort_order": sort_order,
            "show_period_dropdown": show_period_dropdown,
            "display_strings": get_display_strings(order, period),
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


@user_passes_test(lambda u: u.is_superuser)
def switch_account_type(_, accountlookup_id: int, account_type: str):
    accountlookup = AccountLookup.objects.get(id=accountlookup_id)
    accountlookup.account_type = account_type
    accountlookup.save()
    if account_type == "H":
        to_switch = "P"
    else:
        to_switch = "H"

    return HttpResponse(
        f"""<button hx-post="{reverse("switch_account_type", args=[accountlookup_id, to_switch])}" hx-target="#switch_account_type" hx-swap="innerHTML">Switch to {"Human" if to_switch == 'H' else "Project"}</button>"""
    )


@cache_page(60 * 60 * 24, cache="memory")
def faq(request):
    instances = Instance.objects.values_list("instance", flat=True)
    return render(
        request,
        "faq.html",
        {
            "page_title": "FediDevs | FAQ",
            "page_header": "FEDIDEVS FAQ",
            "page_description": "Frequently Asked Questions",
            "page_image": "faq.png",
            "instances": instances,
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
