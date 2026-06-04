from django.db import migrations
from django.db.models import F, TextField, Value
from django.db.models.functions import Concat


def fix_misskey_activitypub_ids(apps, _):
    """Repair Misskey-family local accounts whose actor URI was stored as the
    profile URL.

    The adapter used to fall back to ``url`` (https://host/@username) when the
    native /api/users payload had a null ``uri``, so ``activitypub_id`` ended up
    equal to ``url``. The real ActivityPub actor URI is https://host/users/{id},
    and the Misskey id is what we already store in ``account_id`` (and the host
    in ``instance``), so rebuild it from those columns.

    Signature of the affected rows: ``activitypub_id == url`` and ``url`` is the
    ``/@username`` profile form. Healthy Mastodon rows never match this (their
    ``uri`` uses ``/users/`` and differs from ``url``), and the already-null rows
    don't match either, so this is a no-op for everything except the buggy rows.
    """
    Account = apps.get_model("accounts", "Account")
    Account.objects.filter(activitypub_id=F("url"), url__contains="/@").update(
        activitypub_id=Concat(
            Value("https://"),
            F("instance"),
            Value("/users/"),
            F("account_id"),
            output_field=TextField(),
        )
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0034_account_accounts_ac_usernam_ecd7da_idx"),
    ]

    operations = [
        # Reverse is a no-op: re-introducing the buggy /@username actor URI would
        # serve no purpose, and the fixed value is unambiguously correct.
        migrations.RunPython(fix_misskey_activitypub_ids, migrations.RunPython.noop),
    ]
