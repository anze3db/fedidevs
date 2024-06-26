# Generated by Django 5.1a1 on 2024-06-21 22:27

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("stats", "0013_daily_opentofu_accounts_daily_opentofu_posts_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="DailySite",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(db_index=True, unique=True)),
                ("total_users", models.IntegerField()),
                ("daily_active_users", models.IntegerField()),
                ("weekly_active_users", models.IntegerField()),
                ("monthly_active_users", models.IntegerField()),
                ("total_follows", models.IntegerField()),
                ("daily_follows", models.IntegerField()),
                ("weekly_follows", models.IntegerField()),
                ("monthly_follows", models.IntegerField()),
            ],
        ),
    ]
