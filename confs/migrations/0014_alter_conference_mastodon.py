# Generated by Django 5.1a1 on 2024-06-14 15:47

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("confs", "0013_alter_conferencelookup_language"),
    ]

    operations = [
        migrations.AlterField(
            model_name="conference",
            name="mastodon",
            field=models.URLField(blank=True, default=""),
        ),
    ]
