# Generated by Django 4.2.7 on 2023-11-06 10:01

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Fwd50Account",
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
                ("account_id", models.TextField()),
                ("instance", models.TextField()),
                ("username", models.TextField()),
                ("acct", models.TextField()),
                ("display_name", models.TextField()),
                ("locked", models.BooleanField()),
                ("bot", models.BooleanField()),
                ("discoverable", models.BooleanField()),
                ("group", models.BooleanField()),
                ("noindex", models.BooleanField(blank=True, null=True)),
                ("created_at", models.DateTimeField()),
                (
                    "last_status_at",
                    models.DateTimeField(blank=True, db_index=True, null=True),
                ),
                ("last_sync_at", models.DateTimeField()),
                ("followers_count", models.IntegerField(db_index=True)),
                ("following_count", models.IntegerField()),
                ("statuses_count", models.IntegerField(db_index=True)),
                ("note", models.TextField()),
                ("url", models.URLField(db_index=True)),
                ("avatar", models.URLField()),
                ("avatar_static", models.URLField()),
                ("header", models.URLField()),
                ("header_static", models.URLField()),
                ("emojis", models.JSONField()),
                ("roles", models.JSONField()),
                ("fields", models.JSONField()),
            ],
        ),
        migrations.CreateModel(
            name="Fwd50Post",
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
                ("post_id", models.TextField()),
                ("instance", models.TextField()),
                ("created_at", models.DateTimeField()),
                ("in_reply_to_id", models.TextField(blank=True, null=True)),
                ("in_reply_to_account_id", models.TextField(blank=True, null=True)),
                ("sensitive", models.BooleanField(blank=True, null=True)),
                ("spoiler_text", models.TextField(blank=True, null=True)),
                ("visibility", models.TextField()),
                ("language", models.TextField(blank=True, null=True)),
                ("uri", models.URLField()),
                ("url", models.URLField()),
                ("replies_count", models.IntegerField()),
                ("reblogs_count", models.IntegerField()),
                ("favourites_count", models.IntegerField()),
                ("edited_at", models.DateTimeField(blank=True, null=True)),
                ("content", models.TextField()),
                ("reblog", models.TextField(blank=True, null=True)),
                ("application", models.JSONField(blank=True, null=True)),
                ("media_attachments", models.JSONField(default=list)),
                ("mentions", models.JSONField(default=list)),
                ("tags", models.JSONField(default=list)),
                ("emojis", models.JSONField(default=list)),
                ("card", models.JSONField(blank=True, null=True)),
                ("poll", models.JSONField(blank=True, null=True)),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="confs.fwd50account",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="fwd50account",
            index=models.Index(
                fields=["noindex", "discoverable"],
                name="confs_fwd50_noindex_8293c0_idx",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="fwd50account",
            unique_together={("account_id", "instance")},
        ),
        migrations.AlterUniqueTogether(
            name="fwd50post",
            unique_together={("post_id", "instance")},
        ),
    ]
