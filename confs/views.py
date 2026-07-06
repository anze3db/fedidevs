import datetime as dt
import logging
import zoneinfo
from typing import Literal

from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Trunc
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_POST

from accounts.views import build_canonical_url
from confs.models import (
    FRAMEWORKS,
    LANGUAGES,
    Conference,
    ConferenceAccount,
    ConferenceLookup,
    ConferencePost,
    ConferenceTag,
    DjangoConAfricaAccount,
    DjangoConAfricaPost,
    DotNetConfAccount,
    DotNetConfPost,
    Fwd50Account,
    Fwd50Post,
)
from mastodon_auth.models import AccountAccess


def conferences(request, lang: str | None = None):
    language_count_dict = {
        al["language"]: al["count"]
        for al in ConferenceLookup.objects.values("language").annotate(count=Count("language")).order_by("-count")
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

    langs_map = {lng.code: lng for lng in LANGUAGES}
    frameworks_map = {f.code: f for f in FRAMEWORKS}

    selected_lang = langs_map.get(lang)
    selected_framework = frameworks_map.get(lang)
    search_query = Q()
    if selected_lang:
        search_query &= Q(conferencelookup__language=selected_lang.code)
    if selected_framework:
        search_query &= Q(conferencelookup__language=selected_framework.code)

    # Only approved conferences are public. A logged-in submitter also sees their
    # own still-pending submissions (flagged in the template) so they can find the
    # page again while it waits for review.
    approved_query = Q(approved_at__isnull=False)
    if request.user.is_authenticated:
        approved_query |= Q(created_by=request.user)
    search_query &= approved_query

    today = timezone.now().date()
    upcoming_conferences = (
        Conference.objects.filter(start_date__gt=today)
        .prefetch_related("conferencelookup_set", "conference_tags")
        .annotate(posts_count=Count("conferencepost", filter=Q(conferencepost__created_at__gt=F("posts_after"))))
        .filter(search_query)
        .order_by("start_date")
    )
    live_conferences = (
        Conference.objects.filter(start_date__lte=today, end_date__gte=today)
        .filter(search_query)
        .prefetch_related("conferencelookup_set", "conference_tags")
        .annotate(posts_count=Count("conferencepost", filter=Q(conferencepost__created_at__gt=F("posts_after"))))
        .order_by("start_date")
    )
    past_conferences = (
        Conference.objects.filter(end_date__lt=today)
        .prefetch_related("conferencelookup_set", "conference_tags")
        .annotate(posts_count=Count("conferencepost", filter=Q(conferencepost__created_at__gt=F("posts_after"))))
        .filter(search_query)
        .order_by("-start_date")
    )

    frameworks = sorted(
        [f for f in frameworks if f["count"] > 0],
        key=lambda framework: framework["count"],
        reverse=True,
    )
    languages = sorted(
        [lang for lang in languages if lang["count"] > 0],
        key=lambda lng: lng["count"],
        reverse=True,
    )
    if selected_lang:
        title = selected_lang.name + " conference discussions on Mastodon"
    elif selected_framework:
        title = selected_framework.name + " conference discussions on Mastodon"
    else:
        title = "Conference dicussions on Mastodon"
    return render(
        request,
        "conferences.html",
        {
            "page_title": title,
            "page": "conferences",
            "page_header": "Conferences",
            "page_subheader": "",
            "page_description": "",
            "page_image": static("og-conferences.png"),
            "is_superuser": request.user.is_superuser,
            "upcoming_conferences": upcoming_conferences,
            "live_conferences": live_conferences,
            "past_conferences": past_conferences,
            "languages": languages,
            "frameworks": frameworks,
            "selected_lang": selected_lang,
            "selected_framework": selected_framework,
        },
    )


def get_order_display(order: Literal["-favourites_count", "-reblogs_count", "-replies_count", "-created_at"]):
    match order:
        case "-favourites_count":
            return "Favorites"
        case "-reblogs_count":
            return "Boosts"
        case "-replies_count":
            return "Replies"
        case "-created_at":
            return "Created Date"


def conference(request, conference_slug: str):
    # Authenticated users must never be served a stale cached page: staff need to
    # see the approve button, and a submitter previewing their pending conference
    # needs the up-to-date "pending review" state. Only anonymous traffic (the hot
    # path for approved, public conferences) is cached.
    if request.user.is_authenticated:
        return _conference_detail(request, conference_slug)
    return _conference_detail_cached(request, conference_slug)


def _conference_detail(request, conference_slug: str):
    conference = get_object_or_404(Conference, slug=conference_slug)
    if conference.posts_after:
        search_query = Q(conference=conference, created_at__gte=conference.posts_after_datetime)
    else:
        search_query = Q(
            conference=conference,
        )

    order = request.GET.get("o")
    if not order:
        order = request.GET.get("order")

    try:
        account_id = int(request.GET.get("account"))
    except ValueError, TypeError:
        account_id = None
    if account_id:
        search_query &= Q(account_id=account_id)

    date = request.GET.get("date") or None
    if date and (date := parse_date(date)):
        search_query &= Q(
            created_at_date__date__gte=date,
            created_at_date__date__lt=date + dt.timedelta(days=1),
        )

    all_conf_posts_count = (
        ConferencePost.objects.annotate(
            created_at_date=Trunc("created_at", "day", tzinfo=zoneinfo.ZoneInfo(conference.time_zone))
        )
        .filter(search_query)
        .count()
    )
    if order not in ("-favourites_count", "-reblogs_count", "-replies_count", "-created_at"):
        if conference.start_date <= timezone.now().date() <= conference.end_date:
            order = "-created_at"
        else:
            order = "-favourites_count"

    counts = (
        ConferencePost.objects.annotate(
            created_at_date=Trunc("created_at", "day", tzinfo=zoneinfo.ZoneInfo(conference.time_zone))
        )
        .filter(
            conference=conference,
            visibility="public",
            created_at_date__date__gte=conference.start_date,
            created_at_date__date__lt=conference.end_date + dt.timedelta(days=1),
        )
        .values("created_at_date")
        .annotate(count=Count("id"))
    )

    counts_dict = {c["created_at_date"].date(): c["count"] for c in counts}
    dates = [
        conference.start_date + dt.timedelta(days=i)
        for i in range((conference.end_date - conference.start_date).days + 1)
    ]
    if conference.days.strip():
        day_names = {i: n.strip() for i, n in enumerate(conference.days.strip().split(","))}
    else:
        day_names = {}
    if conference.day_styles.strip():
        day_styles = {i: s.strip() for i, s in enumerate(conference.day_styles.strip().split(","))}
    else:
        day_styles = {}
    dates = [
        {
            "value": date,
            "pre_display": f"Day {i + 1}" + (f": {day_names[i]}" if day_names.get(i) else ""),
            "display": date,
            "day_style": day_styles.get(i, ""),
            "count": counts_dict.get(date, 0),
        }
        for i, date in enumerate(dates)
    ]

    conf_posts = (
        ConferencePost.objects.annotate(
            created_at_date=Trunc("created_at", "day", tzinfo=zoneinfo.ZoneInfo(conference.time_zone))
        )
        .filter(search_query & Q(post__account__instance_model__deleted_at__isnull=True))
        .order_by(order)
        .prefetch_related("post", "post__account", "post__account__accountlookup", "post__account__instance_model")
    )

    account_counts = (
        ConferenceAccount.objects.filter(conference=conference)
        .select_related("account")
        .filter(count__gt=0, account__instance_model__deleted_at__isnull=True)
        .order_by("-count")[:10]
    )

    paginator = Paginator(conf_posts, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    user_instance = None
    if request.user.is_authenticated:
        try:
            user_instance = str(request.user.accountaccess.instance)
        except AccountAccess.DoesNotExist:
            pass

    current_account = next((account for account in account_counts if account.account.id == account_id), None)
    current_date = next((d for d in dates if d["value"] == date), None)
    if all_conf_posts_count > 0:
        page_description = f"Dive into {all_conf_posts_count} insightful Mastodon posts from {conference.name} {conference.start_date.strftime('%Y')}"
        if current_account:
            page_description += f" by {current_account.account.name}"
        if current_date:
            page_description += f" on {current_date['pre_display']}"
        page_description += " featuring key discussions, trending topics, and highlights from the conference."
    else:
        page_description = f"Explore Mastodon posts about {conference.name} {conference.start_date.strftime('%Y')}"
    if current_account and current_date:
        page_title = f"{current_account.account.name} Mastodon posts from {current_date['pre_display']} of {conference.name} {conference.start_date.strftime('%Y')}"
    elif current_account and not current_date:
        page_title = f"{current_account.account.name} Mastodon posts from {conference.name} {conference.start_date.strftime('%Y')}"
    elif not current_account and current_date:
        page_title = f"Mastodon posts from {current_date['pre_display']} of {conference.name} {conference.start_date.strftime('%Y')}"
    else:
        page_title = f"{conference.name} {conference.start_date.strftime('%Y')} Mastodon posts and highlights"
    return render(
        request,
        "conference.html" if "HX-Request" not in request.headers else "conference.html#posts-partial",
        {
            "page_title": page_title,
            "page": "conferences",
            # Conference header is conference.name and year
            "page_header": conference.name + " " + conference.start_date.strftime("%Y"),
            "page_header_color": "red",
            "primary_tag": next(tag for tag in conference.tags.split(",") if tag),
            "page_subheader": f"{conference.start_date.strftime('%b %d')} - {conference.end_date.strftime('%b %d, %Y')}",
            "page_description": page_description,
            "canonical_url": build_canonical_url(
                reverse("conference", kwargs={"conference_slug": conference.slug}), request.GET, ["account", "date"]
            ),
            "page_image": static("og-conferences.png"),
            "page_url": reverse("conference", kwargs={"conference_slug": conference.slug}),
            "conference": conference,
            "conf_posts": page_obj,
            "account_counts": account_counts,
            "selected_instance": user_instance,
            "slug": conference_slug,
            "account_id": account_id,
            "current_account": current_account,
            "order_display": get_order_display(order),
            "dates": dates,
            "all_conf_posts_count": all_conf_posts_count,
            "posts_date": date,
            "current_date": current_date,
            "order": order,
            "is_superuser": request.user.is_superuser,
            "is_pending": not conference.is_approved,
            "can_approve": request.user.is_staff and not conference.is_approved,
            "can_unapprove": request.user.is_staff and conference.is_approved,
            "can_edit": can_edit_conference(request.user, conference),
        },
    )


# Anonymous traffic is served from a short-lived cache; see `conference` above.
_conference_detail_cached = cache_page(30, cache="memory")(_conference_detail)


# Create your views here.
def fwd50(request, date: dt.date | None = None):
    search_query = Q(
        visibility="public",
    )
    order = request.GET.get("order")
    if order not in ("-favourites_count", "-reblogs_count", "-replies_count", "-created_at"):
        order = "-favourites_count"

    if date:
        date = date.date()
        search_query &= Q(created_at__date__gte=date, created_at__date__lt=date + dt.timedelta(days=1))
    else:
        search_query &= Q()

    try:
        account_id = int(request.GET.get("account"))
    except ValueError, TypeError:
        account_id = None
    if account_id:
        search_query &= Q(account_id=account_id)

    posts = Fwd50Post.objects.filter(search_query).order_by(order)
    # List of date objects. The first one is the date 2023-09-12 and then one item for every day until the current date
    dates = [
        dt.date(2023, 11, 6),
        dt.date(2023, 11, 7),
        dt.date(2023, 11, 8),
    ]

    users_with_most_posts = Fwd50Account.objects.filter().annotate(count=Count("posts")).order_by("-count")[:10]

    counts = (
        Fwd50Post.objects.filter(
            visibility="public",
            created_at__date__gte=min(dates),
            created_at__date__lt=max(dates) + dt.timedelta(days=1),
        )
        .values("created_at__date")
        .annotate(count=Count("id"))
    )
    counts_dict = {c["created_at__date"]: c["count"] for c in counts}

    dates = [
        {
            "value": date,
            "pre_display": f"Day {i + 1}",
            "display": date,
            "count": counts_dict.get(date, 0),
        }
        for i, date in enumerate(dates)
        if date <= timezone.now().date()
    ]
    paginator = Paginator(posts, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    stats = Fwd50Post.objects.filter(
        visibility="public",
        # created_at__lte=dt.date(2023, 10, 20),
        # created_at__gte=dt.date(2023, 10, 16),
    ).aggregate(
        total_posts=Count("id"),
        total_favourites=Sum("favourites_count"),
    )
    return render(
        request,
        "fwd50.html",
        {
            "page_title": "Mastodon posts FWD50 | Most Favourited Mastodon Posts about FWD50",
            "page": "conferences",
            "page_header": "FWD50",
            "page_subheader": "Nov. 6-8, 2023 | Ottawa and online",
            "page_description": "Most Favourited Mastodon Posts about FWD50",
            "page_image": static("og-fwd50.png"),
            "posts": page_obj,
            "users_with_most_posts": users_with_most_posts,
            "total_posts": stats["total_posts"],
            "total_favourites": stats["total_favourites"],
            "posts_date": date,
            "dates": dates,
            "account_id": account_id,
            "order": order,
        },
    )


def djangoconafrica(request, date: dt.date | None = None):
    search_query = Q(
        visibility="public",
    )
    order = request.GET.get("order")
    if order not in ("-favourites_count", "-reblogs_count", "-replies_count", "-created_at"):
        order = "-favourites_count"

    if date:
        date = date.date()
        search_query &= Q(created_at__date__gte=date, created_at__date__lt=date + dt.timedelta(days=1))
    else:
        search_query &= Q()

    try:
        account_id = int(request.GET.get("account"))
    except ValueError, TypeError:
        account_id = None
    if account_id:
        search_query &= Q(account_id=account_id)

    tags = DjangoConAfricaPost.objects.filter().values("tags")
    tags = {tag["name"] for tags in tags for tag in tags["tags"]}

    selected_tag = request.GET.get("tag")
    if selected_tag in tags:
        search_query &= Q(tags__icontains=f'"name": "{selected_tag}"')
    else:
        selected_tag = None

    posts = DjangoConAfricaPost.objects.filter(search_query).prefetch_related("account").order_by(order)
    # List of date objects. The first one is the date 2023-09-12 and then one item for every day until the current date
    dates = [
        dt.date(2023, 11, 7),
        dt.date(2023, 11, 8),
        dt.date(2023, 11, 9),
        dt.date(2023, 11, 10),
        dt.date(2023, 11, 11),
    ]

    users_with_most_posts = (
        DjangoConAfricaAccount.objects.filter().annotate(count=Count("posts")).order_by("-count")[:10]
    )

    counts = (
        DjangoConAfricaPost.objects.filter(
            visibility="public",
            created_at__date__gte=min(dates),
            created_at__date__lt=max(dates) + dt.timedelta(days=1),
        )
        .values("created_at__date")
        .annotate(count=Count("id"))
    )
    counts_dict = {c["created_at__date"]: c["count"] for c in counts}

    dates = [
        {
            "value": date,
            "pre_display": f"Day {i + 1}",
            "display": date,
            "count": counts_dict.get(date, 0),
        }
        for i, date in enumerate(dates)
        if date <= timezone.now().date()
    ]
    paginator = Paginator(posts, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    stats = DjangoConAfricaPost.objects.filter(
        visibility="public",
        # created_at__lte=dt.date(2023, 10, 20),
        # created_at__gte=dt.date(2023, 10, 16),
    ).aggregate(
        total_posts=Count("id"),
        total_favourites=Sum("favourites_count"),
        total_reblogs=Sum("reblogs_count"),
    )
    return render(
        request,
        "djangoconafrica.html",
        {
            "page_title": "Mastodon posts | Most Favourited Mastodon Posts about #djangoconafrica",
            "page": "conferences",
            "page_header": "DjangoCon Africa",
            "page_subheader": "Nov 6 - 11, 2023 | Zanzibar, Tanzania",
            "page_description": "Most Favourited Mastodon Posts about #djangoconafrica",
            "page_image": static("og-djangoconafrica.png"),
            "posts": page_obj,
            "users_with_most_posts": users_with_most_posts,
            "stats": stats,
            "posts_date": date,
            "dates": dates,
            "account_id": account_id,
            "order": order,
            "tags": sorted(tags),
            "selected_tag": selected_tag,
        },
    )


def dotnetconf(request, date: dt.date | None = None):
    search_query = Q(
        visibility="public",
    )
    order = request.GET.get("order")
    if order not in ("-favourites_count", "-reblogs_count", "-replies_count", "-created_at"):
        order = "-favourites_count"

    if date:
        date = date.date()
        search_query &= Q(created_at__date__gte=date, created_at__date__lt=date + dt.timedelta(days=1))
    else:
        search_query &= Q(
            created_at__date__gte=dt.date(2023, 11, 1),
        )

    try:
        account_id = int(request.GET.get("account"))
    except ValueError, TypeError:
        account_id = None
    if account_id:
        search_query &= Q(account_id=account_id)

    tags = DotNetConfPost.objects.filter().values("tags")
    tags = {tag["name"] for tags in tags for tag in tags["tags"]}

    selected_tag = request.GET.get("tag")
    if selected_tag in tags:
        search_query &= Q(tags__icontains=f'"name": "{selected_tag}"')
    else:
        selected_tag = None

    posts = DotNetConfPost.objects.filter(search_query).prefetch_related("account").order_by(order)
    # List of date objects. The first one is the date 2023-09-12 and then one item for every day until the current date
    dates = [
        dt.date(2023, 11, 14),
        dt.date(2023, 11, 15),
        dt.date(2023, 11, 16),
    ]

    users_with_most_posts = (
        DotNetConfAccount.objects.filter(posts__created_at__date__gte=dt.date(2023, 11, 1))
        .annotate(count=Count("posts"))
        .order_by("-count")[:10]
    )

    counts = (
        DotNetConfPost.objects.filter(
            visibility="public",
            created_at__date__gte=min(dates),
            created_at__date__lt=max(dates) + dt.timedelta(days=1),
        )
        .values("created_at__date")
        .annotate(count=Count("id"))
    )
    counts_dict = {c["created_at__date"]: c["count"] for c in counts}

    dates = [
        {
            "value": date,
            "pre_display": f"Day {i + 1}",
            "display": date,
            "count": counts_dict.get(date, 0),
        }
        for i, date in enumerate(dates)
        if date <= timezone.now().date()
    ]
    paginator = Paginator(posts, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    stats = DotNetConfPost.objects.filter(
        visibility="public",
        # created_at__lte=dt.date(2023, 10, 20),
        created_at__date__gte=dt.date(2023, 11, 1),
    ).aggregate(
        total_posts=Count("id"),
        total_favourites=Sum("favourites_count"),
        total_reblogs=Sum("reblogs_count"),
    )
    return render(
        request,
        "dotnetcon.html",
        {
            "page_title": ".NET Conf 2023 | Most Favourited Mastodon Posts about .NET Conf 2023",
            "page": "conferences",
            "page_header": ".NET Conf 2023",
            "page_subheader": "Nov 14-16, 2023",
            "page_description": "Most Favourited Mastodon Posts about #dotnetconf",
            "page_image": static("og-dotnetconf.png"),
            "posts": page_obj,
            "users_with_most_posts": users_with_most_posts,
            "stats": stats,
            "posts_date": date,
            "dates": dates,
            "account_id": account_id,
            "order": order,
            "tags": sorted(tags),
            "selected_tag": selected_tag,
        },
    )


logger = logging.getLogger(__name__)


INPUT_CLASS = (
    "bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-primary-600 "
    "focus:border-primary-600 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 "
    "dark:placeholder-gray-400 dark:text-white dark:focus:ring-primary-500 dark:focus:border-primary-500"
)

# How many ConferenceTag icons a conference may show in the list.
MAX_CONFERENCE_TAGS = 3


class ConferenceForm(forms.ModelForm):
    # A fediverse profile is a handle (@name@instance.social), not a URL, so this
    # is a plain CharField (not the model's URLField) and we normalise it to a
    # profile URL in clean_mastodon.
    mastodon = forms.CharField(
        required=False,
        help_text="e.g. @djangocon@fosstodon.org or https://fosstodon.org/@djangocon (optional).",
    )

    # The site is served in English (<html lang="en">), which makes browsers
    # render native date pickers in US format (mm/dd/yyyy). Force day-first via
    # lang="en-GB" on the inputs only, so the page stays English while the date
    # fields read as European (dd/mm/yyyy). The value/submission is always ISO
    # regardless of the displayed format, so we pin format/input_formats to ISO.
    _DATE_ATTRS = {"type": "date", "lang": "en-GB"}
    start_date = forms.DateField(
        widget=forms.DateInput(attrs=_DATE_ATTRS, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs=_DATE_ATTRS, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
    )

    class Meta:
        model = Conference
        fields = [
            "name",
            "location",
            "start_date",
            "end_date",
            "time_zone",
            "website",
            "mastodon",
            "description",
            "tags",
            # Icons to render in the conference list; picked from ConferenceTag.
            "conference_tags",
            # Populated by the day builder in the "Advanced" section of the form.
            "days",
            "day_styles",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
            "tags": forms.TextInput(),
            "days": forms.HiddenInput(),
            "day_styles": forms.HiddenInput(),
        }
        help_texts = {
            "tags": "Comma separated hashtags used to gather posts, e.g. #djangocon, #pycon",
            "website": "e.g. https://djangocon.eu",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.HiddenInput):
                continue
            field.widget.attrs.setdefault("class", INPUT_CLASS)

    def clean_conference_tags(self):
        tags = self.cleaned_data.get("conference_tags")
        if tags and len(tags) > MAX_CONFERENCE_TAGS:
            raise forms.ValidationError(_("You can pick at most %(count)d icons.") % {"count": MAX_CONFERENCE_TAGS})
        return tags

    def clean_mastodon(self):
        value = (self.cleaned_data.get("mastodon") or "").strip()
        if not value:
            return ""
        if value.startswith(("http://", "https://")):
            return value
        # Fediverse handle: @name@instance.social (leading @ optional).
        handle = value.lstrip("@")
        user, _sep, instance = handle.partition("@")
        if user and instance and "@" not in instance:
            return f"https://{instance}/@{user}"
        raise forms.ValidationError(_("Enter a fediverse handle like @name@instance.social or a full profile URL."))

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", _("The end date can't be before the start date."))
        return cleaned_data


def conference_tag_context(form: ConferenceForm) -> dict:
    """Context for the icon picker: all available tags and the ids currently
    selected (from the instance, or the submitted data on a failed POST)."""
    selected_tag_ids = set()
    for pk in form["conference_tags"].value() or []:
        try:
            selected_tag_ids.add(int(pk))
        except TypeError, ValueError:
            continue
    return {
        "all_conference_tags": ConferenceTag.objects.all(),
        "selected_tag_ids": selected_tag_ids,
        "max_conference_tags": MAX_CONFERENCE_TAGS,
    }


def unique_conference_slug(name: str) -> str:
    """A slugified, collision-free slug for a new conference."""
    base = slugify(name) or "conference"
    slug = base
    suffix = 2
    while Conference.objects.filter(slug=slug).exists():
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


@login_required
def create_conference(request):
    if request.method == "POST":
        form = ConferenceForm(request.POST)
        if form.is_valid():
            conference = form.save(commit=False)
            conference.slug = unique_conference_slug(conference.name)
            conference.created_by = request.user
            # Start collecting posts from the conference start date by default.
            conference.posts_after = conference.start_date
            # No tag given? Fall back to the slug so the detail page (which needs a
            # primary tag) and post gathering still work, mirroring the old import.
            if not conference.tags.strip():
                conference.tags = conference.slug
            # approved_at stays NULL: pending review until a staff member approves.
            conference.save()
            form.save_m2m()  # persist the selected conference_tags (icons)

            # Account gathering starts automatically: saving a new Conference fires
            # the post_save signal in confs/apps.py, which enqueues findinstances +
            # stattag for this slug. Here we only need to notify the reviewer.
            transaction.on_commit(lambda: send_approval_notification(request, conference))

            return redirect("conference", conference_slug=conference.slug)
    else:
        form = ConferenceForm()

    return render(
        request,
        "conference_form.html",
        {
            "page": "create_conference",
            "page_title": _("Add a conference"),
            "page_description": _("Add a conference to FediDevs to follow the fediverse conversation about it."),
            "page_header": "FEDIDEVS",
            "page_subheader": "",
            "form": form,
            "form_title": _("Add a conference"),
            "submit_label": _("Submit conference"),
            "is_edit": False,
            **conference_tag_context(form),
        },
    )


def can_edit_conference(user, conference: Conference) -> bool:
    """Staff can edit any conference; a submitter can edit their own."""
    if not user.is_authenticated:
        return False
    return user.is_staff or (conference.created_by_id is not None and conference.created_by_id == user.id)


@login_required
def edit_conference(request, conference_slug: str):
    conference = get_object_or_404(Conference, slug=conference_slug)
    if not can_edit_conference(request.user, conference):
        return HttpResponseForbidden()

    if request.method == "POST":
        form = ConferenceForm(request.POST, instance=conference)
        if form.is_valid():
            form.save()
            return redirect("conference", conference_slug=conference.slug)
    else:
        form = ConferenceForm(instance=conference)

    return render(
        request,
        "conference_form.html",
        {
            "page": "conferences",
            "page_title": _("Edit conference"),
            "page_description": "",
            "page_header": "FEDIDEVS",
            "page_subheader": "",
            "form": form,
            "form_title": _("Edit conference"),
            "submit_label": _("Save changes"),
            "is_edit": True,
            "conference": conference,
            **conference_tag_context(form),
        },
    )


@login_required
@require_POST
def approve_conference(request, conference_slug: str):
    if not request.user.is_staff:
        return HttpResponseForbidden()
    conference = get_object_or_404(Conference, slug=conference_slug)
    if not conference.is_approved:
        conference.approved_at = timezone.now()
        conference.save(update_fields=["approved_at"])
    return redirect("conference", conference_slug=conference.slug)


@login_required
@require_POST
def unapprove_conference(request, conference_slug: str):
    if not request.user.is_staff:
        return HttpResponseForbidden()
    conference = get_object_or_404(Conference, slug=conference_slug)
    if conference.is_approved:
        conference.approved_at = None
        conference.save(update_fields=["approved_at"])
    return redirect("conference", conference_slug=conference.slug)


def send_approval_notification(request, conference: Conference) -> None:
    """Email the reviewer that a new conference is waiting for approval."""
    conference_url = request.build_absolute_uri(reverse("conference", kwargs={"conference_slug": conference.slug}))
    submitter = conference.created_by.get_username() if conference.created_by else "an anonymous user"
    subject = f"New conference pending review: {conference.name}"
    body = (
        f"{submitter} submitted a new conference to FediDevs.\n\n"
        f"Name: {conference.name}\n"
        f"Location: {conference.location}\n"
        f"Dates: {conference.start_date} - {conference.end_date}\n"
        f"Website: {conference.website}\n"
        f"Tags: {conference.tags}\n\n"
        f"Review and approve it here (Approve button visible to staff):\n{conference_url}\n"
    )
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [settings.CONFERENCE_APPROVAL_EMAIL],
        )
    except Exception:
        # A mail hiccup shouldn't lose the submission; it's already saved.
        logger.exception("Failed to send conference approval notification for %s", conference.slug)
