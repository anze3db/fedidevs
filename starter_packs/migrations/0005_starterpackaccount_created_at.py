# Generated by Django 5.1.5 on 2025-01-29 23:23

import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def set_created_at_and_created_by_from_starter_pack(apps, _):
    StarterPack = apps.get_model("starter_packs", "StarterPack")
    StarterPackAccount = apps.get_model("starter_packs", "StarterPackAccount")

    for starter_pack in StarterPack.objects.all():
        StarterPackAccount.objects.filter(starter_pack=starter_pack).update(
            created_at=starter_pack.created_at, created_by=starter_pack.created_by
        )


class Migration(migrations.Migration):
    dependencies = [
        ("starter_packs", "0004_starterpack_published_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="starterpackaccount",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="starterpackaccount",
            name="created_by",
            field=models.ForeignKey(
                default=1, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL
            ),
            preserve_default=False,
        ),
        migrations.RunPython(
            set_created_at_and_created_by_from_starter_pack,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
