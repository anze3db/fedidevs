# Generated by Django 4.1.7 on 2023-02-28 10:40

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Account",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("username", models.TextField()),
                ("acct", models.TextField()),
                ("display_name", models.TextField()),
                ("locked", models.BooleanField()),
                ("bot", models.BooleanField()),
                ("discoverable", models.BooleanField()),
                ("group", models.BooleanField()),
                ("noindex", models.BooleanField()),
                ("created_at", models.DateTimeField()),
                ("last_status_at", models.DateTimeField()),
                ("last_sync_at", models.DateTimeField()),
                ("followers_count", models.IntegerField()),
                ("following_count", models.IntegerField()),
                ("statuses_count", models.IntegerField()),
                ("note", models.TextField()),
                ("url", models.URLField()),
                ("avatar", models.URLField()),
                ("avatar_static", models.URLField()),
                ("header", models.URLField()),
                ("header_static", models.URLField()),
                ("emojis", models.JSONField()),
                ("roles", models.JSONField()),
                ("fields", models.JSONField()),
            ],
        ),
    ]
