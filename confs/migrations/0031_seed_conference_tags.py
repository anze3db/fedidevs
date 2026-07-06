from django.db import migrations

from confs.models import FRAMEWORKS, LANGUAGES


def seed_conference_tags(apps, _schema_editor):
    """Populate ConferenceTag with one row per language/framework so the
    submission form's icon picker offers the same icons the conference list
    auto-detects via ConferenceLookup. Idempotent (keyed on slug), so it also
    fixes any pre-existing hand-made rows (e.g. the misspelled python icon)."""

    ConferenceTag = apps.get_model("confs", "ConferenceTag")
    for lang in LANGUAGES + FRAMEWORKS:
        ConferenceTag.objects.update_or_create(
            slug=lang.code,
            defaults={"name": lang.name, "icon": lang.image},
        )


def remove_conference_tags(apps, _schema_editor):

    ConferenceTag = apps.get_model("confs", "ConferenceTag")
    ConferenceTag.objects.filter(slug__in=[lang.code for lang in LANGUAGES + FRAMEWORKS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("confs", "0030_conference_conference_tags_alter_conferencetag_icon"),
    ]

    operations = [
        migrations.RunPython(seed_conference_tags, remove_conference_tags),
    ]
