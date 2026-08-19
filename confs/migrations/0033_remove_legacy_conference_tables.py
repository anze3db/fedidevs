import datetime as dt
import json

from django.db import migrations
from django.db.models import Count
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

LEGACY_SLUGS = ("fwd50", "djangoconafrica", "dotnetconf", "djangoconus23")

ACCOUNT_COPY_FIELDS = (
    "account_id",
    "instance",
    "username",
    "acct",
    "display_name",
    "locked",
    "bot",
    "discoverable",
    "group",
    "noindex",
    "created_at",
    "last_status_at",
    "last_sync_at",
    "followers_count",
    "following_count",
    "statuses_count",
    "note",
    "url",
    "avatar",
    "avatar_static",
    "header",
    "header_static",
    "emojis",
    "roles",
    "fields",
)

POST_COPY_FIELDS = (
    "post_id",
    "instance",
    "created_at",
    "in_reply_to_id",
    "in_reply_to_account_id",
    "sensitive",
    "spoiler_text",
    "visibility",
    "language",
    "uri",
    "url",
    "replies_count",
    "reblogs_count",
    "favourites_count",
    "edited_at",
    "content",
    "reblog",
    "application",
    "media_attachments",
    "mentions",
    "tags",
    "emojis",
    "card",
    "poll",
)


def parse_datetime_value(value):
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        if timezone.is_naive(value):
            return timezone.make_aware(value, dt.UTC)
        return value
    parsed = parse_datetime(str(value))
    if parsed is None:
        parsed_date = parse_date(str(value))
        if parsed_date is None:
            return None
        return dt.datetime.combine(parsed_date, dt.time.min, tzinfo=dt.UTC)
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, dt.UTC)
    return parsed


def _bool(value, default=False):
    if value is None:
        return default
    return bool(value)


def _int(value, default=0):
    if value is None or value == "":
        return default
    try:
        return int(value)
    except TypeError, ValueError:
        return default


def _json_list(value):
    return value if isinstance(value, list) else []


def _text(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


def account_kwargs_from_json(account_json, fallback_instance=""):
    """Build Account field kwargs from a Mastodon account object (DjangoCon US 2023)."""
    if not isinstance(account_json, dict):
        return None
    url = (account_json.get("url") or "").strip()
    username = account_json.get("username") or ""
    instance = fallback_instance or ""
    if url.startswith("http://") or url.startswith("https://"):
        instance = url.split("/")[2]
    elif username and instance:
        url = f"https://{instance}/@{username}"
    account_id = str(account_json.get("id") or "")
    if not account_id or not url or not instance:
        return None
    created_at = parse_datetime_value(account_json.get("created_at")) or timezone.now()
    last_sync_at = parse_datetime_value(account_json.get("last_sync_at")) or created_at
    return {
        "account_id": account_id,
        "instance": instance,
        "username": username,
        "acct": account_json.get("acct") or username,
        "display_name": account_json.get("display_name") or "",
        "locked": _bool(account_json.get("locked")),
        "bot": _bool(account_json.get("bot")),
        "discoverable": _bool(account_json.get("discoverable")),
        "group": _bool(account_json.get("group")),
        "noindex": account_json.get("noindex"),
        "created_at": created_at,
        "last_status_at": parse_datetime_value(account_json.get("last_status_at")),
        "last_sync_at": last_sync_at,
        "followers_count": _int(account_json.get("followers_count")),
        "following_count": _int(account_json.get("following_count")),
        "statuses_count": _int(account_json.get("statuses_count")),
        "note": account_json.get("note") or "",
        "url": url,
        "avatar": account_json.get("avatar") or "",
        "avatar_static": account_json.get("avatar_static") or account_json.get("avatar") or "",
        "header": account_json.get("header") or "",
        "header_static": account_json.get("header_static") or account_json.get("header") or "",
        "emojis": _json_list(account_json.get("emojis")),
        "roles": _json_list(account_json.get("roles")),
        "fields": _json_list(account_json.get("fields")),
        "username_at_instance": f"@{username}@{instance}".lower() if username else "",
    }


def legacy_account_to_dict(account):
    data = {field: getattr(account, field) for field in ACCOUNT_COPY_FIELDS}
    data["username_at_instance"] = f"@{account.username}@{account.instance}".lower()
    data["emojis"] = _json_list(data.get("emojis"))
    data["roles"] = _json_list(data.get("roles"))
    data["fields"] = _json_list(data.get("fields"))
    return data


def legacy_post_to_dict(post, account):
    data = {field: getattr(post, field) for field in POST_COPY_FIELDS}
    data["account"] = account
    data["reblog"] = _text(data.get("reblog"))
    for list_field in ("media_attachments", "mentions", "tags", "emojis"):
        data[list_field] = _json_list(data.get(list_field))
    return data


def _resolve_accounts(account_model, account_dicts):
    by_url = {}
    by_pair = {}
    urls = [d["url"] for d in account_dicts if d.get("url")]
    if urls:
        for account in account_model.objects.filter(url__in=urls):
            by_url[account.url] = account
            by_pair[(account.account_id, account.instance)] = account

    remaining = [d for d in account_dicts if d.get("url") not in by_url]
    if remaining:
        account_ids = {d["account_id"] for d in remaining}
        instances = {d["instance"] for d in remaining}
        for account in account_model.objects.filter(account_id__in=account_ids, instance__in=instances):
            by_pair[(account.account_id, account.instance)] = account
            by_url.setdefault(account.url, account)

    to_create = []
    seen_pairs = set()
    for data in remaining:
        pair = (data["account_id"], data["instance"])
        if data.get("url") in by_url or pair in by_pair or pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        to_create.append(account_model(**data))
    if to_create:
        account_model.objects.bulk_create(to_create, ignore_conflicts=True, batch_size=500)
        created_urls = [account.url for account in to_create]
        for account in account_model.objects.filter(url__in=created_urls):
            by_url[account.url] = account
            by_pair[(account.account_id, account.instance)] = account

    def resolve(data):
        return by_url.get(data.get("url")) or by_pair.get((data["account_id"], data["instance"]))

    return resolve


def _resolve_posts(post_model, post_dicts):
    by_url = {}
    by_pair = {}
    urls = [d["url"] for d in post_dicts if d.get("url")]
    if urls:
        for post in post_model.objects.filter(url__in=urls).select_related("account"):
            by_url[post.url] = post
            by_pair[(post.post_id, post.account_id)] = post

    remaining = [d for d in post_dicts if d.get("url") not in by_url]
    if remaining:
        post_ids = {d["post_id"] for d in remaining}
        account_ids = {d["account"].pk for d in remaining}
        for post in post_model.objects.filter(post_id__in=post_ids, account_id__in=account_ids):
            by_pair[(post.post_id, post.account_id)] = post
            by_url.setdefault(post.url, post)

    to_create = []
    seen_pairs = set()
    for data in remaining:
        pair = (data["post_id"], data["account"].pk)
        if data.get("url") in by_url or pair in by_pair or pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        to_create.append(post_model(**data))
    if to_create:
        post_model.objects.bulk_create(to_create, ignore_conflicts=True, batch_size=500)
        created_urls = [post.url for post in to_create]
        for post in post_model.objects.filter(url__in=created_urls).select_related("account"):
            by_url[post.url] = post
            by_pair[(post.post_id, post.account_id)] = post

    def resolve(data):
        return by_url.get(data.get("url")) or by_pair.get((data["post_id"], data["account"].pk))

    return resolve


def _link_conference_posts(conference, posts, conference_post_model):
    if not posts:
        return
    conference_post_model.objects.bulk_create(
        [
            conference_post_model(
                conference=conference,
                post=post,
                created_at=post.created_at,
                favourites_count=post.favourites_count,
                reblogs_count=post.reblogs_count,
                replies_count=post.replies_count,
                visibility=post.visibility,
                account=post.account,
            )
            for post in posts
        ],
        ignore_conflicts=True,
        batch_size=500,
    )


def _refresh_account_counts(conference, conference_post_model, conference_account_model):
    counts = (
        conference_post_model.objects.filter(conference=conference, account_id__isnull=False)
        .values("account_id")
        .annotate(c=Count("id"))
    )
    conference_account_model.objects.bulk_create(
        [
            conference_account_model(conference=conference, account_id=row["account_id"], count=row["c"])
            for row in counts
        ],
        ignore_conflicts=True,
        batch_size=500,
    )
    for row in counts:
        conference_account_model.objects.filter(conference=conference, account_id=row["account_id"]).update(
            count=row["c"]
        )


def _attach_lookups_and_tags(apps, conference, languages, tag_slugs):
    conference_lookup_model = apps.get_model("confs", "ConferenceLookup")
    conference_tag_model = apps.get_model("confs", "ConferenceTag")
    existing = set(conference_lookup_model.objects.filter(conference=conference).values_list("language", flat=True))
    conference_lookup_model.objects.bulk_create(
        [
            conference_lookup_model(conference=conference, language=language)
            for language in languages
            if language not in existing
        ]
    )
    tags = list(conference_tag_model.objects.filter(slug__in=tag_slugs))
    if tags:
        conference.conference_tags.add(*tags)


def _get_or_create_conference(conference_model, spec, now):
    defaults = {
        "name": spec["name"],
        "location": spec["location"],
        "start_date": spec["start_date"],
        "end_date": spec["end_date"],
        "time_zone": spec["time_zone"],
        "website": spec["website"],
        "mastodon": spec["mastodon"],
        "description": spec["description"],
        "tags": spec["tags"],
        "days": spec["days"],
        "posts_after": spec["start_date"] - dt.timedelta(days=180),
        "archived_date": spec["end_date"] + dt.timedelta(days=15),
        "approved_at": now,
        "instances": "mastodon.social",
    }
    conference, _created = conference_model.objects.get_or_create(slug=spec["slug"], defaults=defaults)
    return conference


def migrate_legacy_pair(apps, conference, account_model, post_model):
    account_model_cls = apps.get_model("accounts", "Account")
    post_model_cls = apps.get_model("posts", "Post")
    conference_post_model = apps.get_model("confs", "ConferencePost")
    conference_account_model = apps.get_model("confs", "ConferenceAccount")

    legacy_accounts = list(account_model.objects.all())
    account_dicts = [legacy_account_to_dict(account) for account in legacy_accounts]
    resolve_account = _resolve_accounts(account_model_cls, account_dicts)
    old_pk_to_account = {}
    for old, data in zip(legacy_accounts, account_dicts, strict=True):
        account = resolve_account(data)
        if account is not None:
            old_pk_to_account[old.pk] = account

    post_dicts = []
    for old_post in post_model.objects.iterator(chunk_size=1000):
        account = old_pk_to_account.get(old_post.account_id)
        if account is None:
            continue
        post_dicts.append(legacy_post_to_dict(old_post, account))
        if len(post_dicts) >= 500:
            resolve_post = _resolve_posts(post_model_cls, post_dicts)
            posts = [post for data in post_dicts if (post := resolve_post(data)) is not None]
            _link_conference_posts(conference, posts, conference_post_model)
            post_dicts = []
    if post_dicts:
        resolve_post = _resolve_posts(post_model_cls, post_dicts)
        posts = [post for data in post_dicts if (post := resolve_post(data)) is not None]
        _link_conference_posts(conference, posts, conference_post_model)
    _refresh_account_counts(conference, conference_post_model, conference_account_model)


def migrate_djangoconus_posts(apps, conference):
    account_model_cls = apps.get_model("accounts", "Account")
    post_model_cls = apps.get_model("posts", "Post")
    conference_post_model = apps.get_model("confs", "ConferencePost")
    conference_account_model = apps.get_model("confs", "ConferenceAccount")
    djangoconus_post_model = apps.get_model("posts", "DjangoConUS23Post")

    batch_accounts = []
    batch_posts = []
    for old_post in djangoconus_post_model.objects.iterator(chunk_size=1000):
        account_data = account_kwargs_from_json(old_post.account, old_post.instance)
        if account_data is None:
            continue
        post_data = legacy_post_to_dict(old_post, account=None)
        batch_accounts.append(account_data)
        batch_posts.append((post_data, account_data))
        if len(batch_posts) >= 500:
            _flush_djangoconus_batch(
                account_model_cls, post_model_cls, conference_post_model, conference, batch_accounts, batch_posts
            )
            batch_accounts = []
            batch_posts = []
    if batch_posts:
        _flush_djangoconus_batch(
            account_model_cls, post_model_cls, conference_post_model, conference, batch_accounts, batch_posts
        )
    _refresh_account_counts(conference, conference_post_model, conference_account_model)


def _flush_djangoconus_batch(account_model, post_model, conference_post_model, conference, batch_accounts, batch_posts):
    resolve_account = _resolve_accounts(account_model, batch_accounts)
    post_dicts = []
    for post_data, account_data in batch_posts:
        account = resolve_account(account_data)
        if account is None:
            continue
        post_fields = dict(post_data)
        post_fields["account"] = account
        post_dicts.append(post_fields)
    if not post_dicts:
        return
    resolve_post = _resolve_posts(post_model, post_dicts)
    posts = [post for data in post_dicts if (post := resolve_post(data)) is not None]
    _link_conference_posts(conference, posts, conference_post_model)


CONFERENCES = (
    {
        "slug": "fwd50",
        "name": "FWD50",
        "location": "Ottawa and online",
        "start_date": dt.date(2023, 11, 6),
        "end_date": dt.date(2023, 11, 8),
        "time_zone": "America/Toronto",
        "website": "https://www.fwd50.com",
        "mastodon": "",
        "description": (
            '<a href="https://www.fwd50.com">FWD50</a> took place on November 6-8, 2023 in Ottawa\'s Lansdowne Park.'
        ),
        "tags": "#fwd50",
        "days": "",
        "languages": (),
        "tag_slugs": (),
        "pair": ("Fwd50Account", "Fwd50Post"),
    },
    {
        "slug": "djangoconafrica",
        "name": "DjangoCon Africa",
        "location": "Zanzibar, Tanzania",
        "start_date": dt.date(2023, 11, 6),
        "end_date": dt.date(2023, 11, 11),
        "time_zone": "Africa/Dar_es_Salaam",
        "website": "https://2023.djangocon.africa",
        "mastodon": "",
        "description": (
            '<a href="https://2023.djangocon.africa">DjangoCon Africa</a> took place on '
            "November 6 - 11, 2023 in Zanzibar, Tanzania."
        ),
        "tags": "#djangoconafrica",
        "days": "",
        "languages": ("python", "django"),
        "tag_slugs": ("python", "django"),
        "pair": ("DjangoConAfricaAccount", "DjangoConAfricaPost"),
    },
    {
        "slug": "dotnetconf",
        "name": ".NET Conf 2023",
        "location": "Online",
        "start_date": dt.date(2023, 11, 14),
        "end_date": dt.date(2023, 11, 16),
        "time_zone": "America/Los_Angeles",
        "website": "https://www.dotnetconf.net",
        "mastodon": "",
        "description": ".NET Conf 2023 took place on November 14-16, 2023.",
        "tags": "#dotnetconf",
        "days": "",
        "languages": ("csharp", "dotnet"),
        "tag_slugs": ("csharp", "dotnet"),
        "pair": ("DotNetConfAccount", "DotNetConfPost"),
    },
    {
        "slug": "djangoconus23",
        "name": "DjangoCon US 2023",
        "location": "Durham, NC",
        "start_date": dt.date(2023, 10, 16),
        "end_date": dt.date(2023, 10, 20),
        "time_zone": "America/New_York",
        "website": "https://2023.djangocon.us",
        "mastodon": "https://fosstodon.org/@djangocon",
        "description": (
            '<a href="https://2023.djangocon.us">2023 DjangoCon US</a> took place on '
            "October 16-20, 2023 in Durham Convention Center in Durham, NC."
        ),
        "tags": "#djangocon, #djangoconus",
        "days": "Talks, Talks, Talks, Sprints, Sprints",
        "languages": ("python", "django"),
        "tag_slugs": ("python", "django"),
        "pair": None,
    },
)


def migrate_legacy_conferences(apps, _schema_editor):
    conference_model = apps.get_model("confs", "Conference")
    now = timezone.now()
    for spec in CONFERENCES:
        conference = _get_or_create_conference(conference_model, spec, now)
        _attach_lookups_and_tags(apps, conference, spec["languages"], spec["tag_slugs"])
        if spec["pair"]:
            account_model = apps.get_model("confs", spec["pair"][0])
            post_model = apps.get_model("confs", spec["pair"][1])
            migrate_legacy_pair(apps, conference, account_model, post_model)
        elif spec["slug"] == "djangoconus23":
            migrate_djangoconus_posts(apps, conference)


def unmigrate_legacy_conferences(apps, _schema_editor):
    conference_model = apps.get_model("confs", "Conference")
    conference_model.objects.filter(slug__in=LEGACY_SLUGS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0035_fix_misskey_activitypub_id"),
        ("confs", "0032_conference_og_image_conference_og_image_needs_update_and_more"),
        ("posts", "0006_post_posts_post_account_7eef7a_idx"),
    ]

    operations = [
        migrations.RunPython(migrate_legacy_conferences, unmigrate_legacy_conferences),
        migrations.AlterUniqueTogether(
            name="djangoconafricaaccount",
            unique_together=None,
        ),
        migrations.RemoveIndex(
            model_name="djangoconafricaaccount",
            name="confs_djang_noindex_e2231b_idx",
        ),
        migrations.RemoveConstraint(
            model_name="djangoconafricaaccount",
            name="unique_djangoconafrica_url",
        ),
        migrations.AlterUniqueTogether(
            name="djangoconafricapost",
            unique_together=None,
        ),
        migrations.RemoveConstraint(
            model_name="djangoconafricapost",
            name="unique_post_djangoconafrica_url",
        ),
        migrations.AlterUniqueTogether(
            name="dotnetconfaccount",
            unique_together=None,
        ),
        migrations.RemoveIndex(
            model_name="dotnetconfaccount",
            name="confs_dotne_noindex_cf758a_idx",
        ),
        migrations.RemoveConstraint(
            model_name="dotnetconfaccount",
            name="unique_dotnetcon_url",
        ),
        migrations.AlterUniqueTogether(
            name="dotnetconfpost",
            unique_together=None,
        ),
        migrations.RemoveConstraint(
            model_name="dotnetconfpost",
            name="unique_post_dotnetcon_url",
        ),
        migrations.AlterUniqueTogether(
            name="fwd50account",
            unique_together=None,
        ),
        migrations.RemoveIndex(
            model_name="fwd50account",
            name="confs_fwd50_noindex_8293c0_idx",
        ),
        migrations.RemoveConstraint(
            model_name="fwd50account",
            name="unique_account_url",
        ),
        migrations.AlterUniqueTogether(
            name="fwd50post",
            unique_together=None,
        ),
        migrations.RemoveConstraint(
            model_name="fwd50post",
            name="unique_post_url",
        ),
        migrations.RemoveField(
            model_name="djangoconafricapost",
            name="account",
        ),
        migrations.RemoveField(
            model_name="dotnetconfpost",
            name="account",
        ),
        migrations.RemoveField(
            model_name="fwd50post",
            name="account",
        ),
        migrations.DeleteModel(
            name="DjangoConAfricaAccount",
        ),
        migrations.DeleteModel(
            name="DjangoConAfricaPost",
        ),
        migrations.DeleteModel(
            name="DotNetConfAccount",
        ),
        migrations.DeleteModel(
            name="DotNetConfPost",
        ),
        migrations.DeleteModel(
            name="Fwd50Account",
        ),
        migrations.DeleteModel(
            name="Fwd50Post",
        ),
    ]
