# Generated by Django 5.0.3 on 2024-03-25 10:32

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("stats", "0007_daily_kubernetes_accounts_daily_kubernetes_posts_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="daily",
            name="julia_accounts",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="daily",
            name="julia_posts",
            field=models.IntegerField(default=0),
        ),
    ]