# Generated by Django 5.2.4 on 2025-07-29 23:09

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0031_instance_private"),
    ]

    operations = [
        migrations.AddField(
            model_name="account",
            name="activitypub_id",
            field=models.URLField(null=True),
        ),
    ]
