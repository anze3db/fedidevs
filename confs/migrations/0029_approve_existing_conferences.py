from django.db import migrations
from django.utils import timezone


def approve_existing(apps, _schema_editor):
    """Every conference that predates the submission/approval flow was added by
    hand (spreadsheet import or admin), so it's implicitly approved. Backfill
    approved_at so nothing currently live disappears from the public site."""
    Conference = apps.get_model("confs", "Conference")
    Conference.objects.filter(approved_at__isnull=True).update(approved_at=timezone.now())


def unapprove(apps, _schema_editor):
    Conference = apps.get_model("confs", "Conference")
    Conference.objects.update(approved_at=None)


class Migration(migrations.Migration):
    dependencies = [
        ("confs", "0028_conference_approved_at_conference_created_by"),
    ]

    operations = [
        migrations.RunPython(approve_existing, unapprove),
    ]
