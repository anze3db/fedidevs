# Generated by Django 5.0.4 on 2024-05-18 08:54

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("stats", "0010_daily_css_accounts_daily_css_posts"),
    ]

    operations = [
        migrations.AddField(
            model_name="daily",
            name="r_accounts",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="daily",
            name="r_posts",
            field=models.IntegerField(default=0),
        ),
    ]
