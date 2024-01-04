# Generated by Django 5.0 on 2024-01-04 15:33

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0014_alter_accountlookup_language"),
        ("confs", "0006_conference"),
        ("posts", "0005_postsubscription"),
    ]

    operations = [
        migrations.AddField(
            model_name="conference",
            name="accounts",
            field=models.ManyToManyField(blank=True, to="accounts.account"),
        ),
        migrations.AddField(
            model_name="conference",
            name="instances",
            field=models.TextField(default=""),
        ),
        migrations.AddField(
            model_name="conference",
            name="mastodon",
            field=models.URLField(default=""),
        ),
        migrations.AddField(
            model_name="conference",
            name="min_id",
            field=models.CharField(default="0", max_length=255),
        ),
        migrations.AddField(
            model_name="conference",
            name="posts",
            field=models.ManyToManyField(blank=True, to="posts.post"),
        ),
        migrations.AddField(
            model_name="conference",
            name="posts_after",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="conference",
            name="tags",
            field=models.TextField(default=""),
        ),
        migrations.AddField(
            model_name="conference",
            name="website",
            field=models.URLField(default=""),
        ),
    ]
