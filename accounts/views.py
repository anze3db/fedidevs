import datetime as dt

from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Q
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import cache_page

from mastodon_auth.models import AccountFollowing
from stats.models import Daily

from .models import FRAMEWORKS, LANGUAGES, Account, AccountLookup, Framework, Instance, Language


def get_lookup_sort_order(order: str, period: str):
    prefix = "-accountlookup__"
    if order == "last_status_at":
        return f"{prefix}last_status_at"

    if order not in (
        "followers",
        "following",
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
    elif order == "following":
        res["order"] = "Following"
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


def get_page_title(
    selected_lang: Language | None,
    selected_framework: Framework | None,
    follower_type: str | None,
    account_type: str | None,
    posted: str | None,
) -> str:
    page_title = ""
    if follower_type == "best":
        page_title += "The best "
    elif follower_type == "popular":
        page_title += "Popular "
    else:
        page_title += "Awesome "

    if selected_lang:
        page_title += f"{selected_lang.name} "
    elif selected_framework:
        page_title += f"{selected_framework.name} "

    if account_type == "human":
        page_title += "developers "
    elif account_type == "project":
        page_title += "projects "
    else:
        page_title += "accounts "

    page_title += "on Mastodon"

    if posted == "recently":
        page_title += " that posted recently"

    return page_title


def get_page_description(
    accounts_count: int,
    selected_lang: Language | None,
    selected_framework: Framework | None,
    follower_type: str | None,
    account_type: str | None,
    posted: str | None,
) -> str:
    page_description = ""
    if accounts_count > 0:
        page_description += f"{accounts_count} "
    else:
        page_description += "No "

    if follower_type == "best" and accounts_count > 0:
        page_description += "of the best "
    elif follower_type == "best":
        page_description += "best "
    elif follower_type == "popular":
        page_description += "popular "
    else:
        page_description += "awesome "

    if selected_lang:
        page_description += f"{selected_lang.name} "
    elif selected_framework:
        page_description += f"{selected_framework.name} "

    if account_type == "human":
        if accounts_count == 1:
            page_description += "developer"
        else:
            page_description += "developers"
    elif account_type == "project":
        if accounts_count == 1:
            page_description += "project"
        else:
            page_description += "projects"
    elif accounts_count == 1:
        page_description += "account"
    else:
        page_description += "accounts"

    page_description += " on Mastodon"
    if posted == "recently":
        page_description += " that posted recently"
    page_description += ". "

    return page_description


def build_canonical_url(base, get_params, canonical_params):
    canonical_url = base
    params_to_include = []
    for param in canonical_params:
        if param in get_params:
            if get_params[param] is not None or get_params[param] != "":
                params_to_include.append(f"{param}={get_params[param]}")
    if params_to_include:
        canonical_url += "?" + "&".join(params_to_include)
    return canonical_url


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
        search_query &= Q(accountlookup__language__icontains=selected_lang.code + "\n")
    if selected_framework:
        search_query &= Q(accountlookup__language__icontains=selected_framework.code + "\n")

    order = request.GET.get("o") or "followers"
    period = request.GET.get("p") or "all"
    query = request.GET.get("q", "").strip()

    account_type = request.GET.get("t")
    if account_type == "human":
        search_query &= Q(accountlookup__account_type="H")
    elif account_type == "project":
        search_query &= Q(accountlookup__account_type="P")

    follower_type = request.GET.get("f")
    if follower_type in ("celebrity", "popular"):
        follower_type = "popular"
        search_query &= Q(accountlookup__follower_type="C")
    elif follower_type == "best":
        search_query &= Q(accountlookup__follower_type="B")

    posted = request.GET.get("post")
    if posted == "recently":
        search_query &= Q(accountlookup__last_status_at__gte=timezone.now() - dt.timedelta(days=7))

    show_period_dropdown = order != "last_status_at"
    sort_order = get_lookup_sort_order(order, period)
    if query:
        search_query &= Q(accountlookup__text__icontains=query)

    accounts = (
        Account.objects.select_related("accountlookup", "instance_model")
        .filter(search_query)
        .only(
            "id",
            "display_name",
            "username",
            "account_id",
            "header",
            "url",
            "instance",
            "avatar",
            "emojis",
            "note",
            "last_status_at",
            "instance_model",
            "accountlookup",
        )
    )
    accounts = accounts.order_by(sort_order)
    if request.user.is_authenticated:
        # Annotate whether the current request user is following the account:
        accounts = accounts.annotate(
            is_following=Exists(
                AccountFollowing.objects.filter(account=request.user.accountaccess.account, url=OuterRef("url")),
            )
        )
    paginator = Paginator(accounts, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    accounts_count = page_obj.paginator.count

    user_instance = None
    if request.user.is_authenticated:
        user_instance = str(request.user.accountaccess.instance)

    instances = Instance.objects.filter(deleted_at__isnull=True).values_list("instance", flat=True)

    page_description = get_page_description(
        accounts_count, selected_lang, selected_framework, follower_type, account_type, posted
    )

    top_five_accounts = ""
    if accounts_count > 0:
        top_five_accounts += ", ".join(a.name for a in page_obj[:5])
        if accounts_count > 5:
            top_five_accounts += ", and more."

    return render(
        request,
        "v2/accounts.html" if "HX-Request" in request.headers else "v2/index.html",
        {
            "page": "accounts",
            "page_title": get_page_title(selected_lang, selected_framework, follower_type, account_type, posted),
            "page_header": "FEDIDEVS",
            "page_subheader": page_description,
            "canonical_url": build_canonical_url(
                reverse("index", kwargs={"lang": lang}), request.GET, ["t", "f", "post"]
            ),
            "page_description": top_five_accounts if top_five_accounts else page_description,
            "page_image": "og.png",
            "accounts": page_obj,
            "selected_lang": selected_lang,
            "selected_framework": selected_framework,
            "selected_lang_or_framework": selected_lang or selected_framework,
            "languages": languages,
            "frameworks": frameworks,
            "instances": instances,
            "account_type": account_type,
            "follower_type": follower_type,
            "posted": posted,
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
    instances = Instance.objects.values("instance", "deleted_at")
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
